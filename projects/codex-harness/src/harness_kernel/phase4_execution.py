"""Lifecycle orchestration for the bounded Phase 4 invocation pilot."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import time
import uuid
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import replace
from pathlib import Path
from threading import Event, Lock

try:
    import fcntl
except ImportError:  # pragma: no cover - the supported CI/runtime is POSIX
    fcntl = None  # type: ignore[assignment]

from .phase3_discovery import revalidate_capability
from .phase3_models import CapabilityInventory, CapabilityRecord, Phase3Limits, ResolutionResult
from .phase4_artifacts import (
    ArtifactCaptureError,
    _mkdir_safe,
    capture_host_response,
    validate_artifact_path,
)
from .phase4_host import CapabilityInvocationAdapter
from .phase4_models import (
    ArtifactRecord,
    AssuranceDecision,
    AssuranceResult,
    CapabilityExecutionAuthorization,
    CapabilityInvocationRequest,
    ExecutionMode,
    ExecutionOutcome,
    HostInvocationResult,
    HostLoadObservation,
    InvocationLifecycle,
    InvocationReceipt,
    InvocationResultStatus,
    Phase4Budget,
    PreparedInvocation,
    VerificationResult,
    digest_payload,
    invocation_receipt_digest,
    stable_digest_payload,
)
from .phase4_policy import ExecutionPolicyRegistry, build_preflight, preflight_digest
from .phase4_verification import validate_receipt_binding, verify_host_result

_TRANSITIONS: dict[InvocationLifecycle, frozenset[InvocationLifecycle]] = {
    InvocationLifecycle.DISCOVERED: frozenset(
        {InvocationLifecycle.RESOLVED, InvocationLifecycle.BLOCKED}
    ),
    InvocationLifecycle.RESOLVED: frozenset(
        {InvocationLifecycle.AUTHORIZED, InvocationLifecycle.BLOCKED}
    ),
    InvocationLifecycle.AUTHORIZED: frozenset(
        {InvocationLifecycle.CONTEXT_PREPARED, InvocationLifecycle.BLOCKED}
    ),
    InvocationLifecycle.CONTEXT_PREPARED: frozenset(
        {
            InvocationLifecycle.INVOCATION_REQUESTED,
            InvocationLifecycle.CLOSED,
            InvocationLifecycle.BLOCKED,
        }
    ),
    InvocationLifecycle.INVOCATION_REQUESTED: frozenset(
        {
            InvocationLifecycle.HOST_ACKNOWLEDGED,
            InvocationLifecycle.FAILED,
            InvocationLifecycle.BLOCKED,
            InvocationLifecycle.TIMED_OUT,
            InvocationLifecycle.CANCELLED,
        }
    ),
    InvocationLifecycle.HOST_ACKNOWLEDGED: frozenset(
        {
            InvocationLifecycle.EXECUTING,
            InvocationLifecycle.FAILED,
            InvocationLifecycle.PARTIAL,
            InvocationLifecycle.TIMED_OUT,
            InvocationLifecycle.CANCELLED,
        }
    ),
    InvocationLifecycle.EXECUTING: frozenset(
        {
            InvocationLifecycle.RESULT_RECEIVED,
            InvocationLifecycle.TIMED_OUT,
            InvocationLifecycle.CANCELLED,
            InvocationLifecycle.FAILED,
            InvocationLifecycle.PARTIAL,
        }
    ),
    InvocationLifecycle.RESULT_RECEIVED: frozenset({InvocationLifecycle.VERIFYING}),
    InvocationLifecycle.VERIFYING: frozenset(
        {
            InvocationLifecycle.VERIFIED,
            InvocationLifecycle.FAILED,
            InvocationLifecycle.PARTIAL,
        }
    ),
    InvocationLifecycle.VERIFIED: frozenset({InvocationLifecycle.CLOSED}),
    InvocationLifecycle.FAILED: frozenset({InvocationLifecycle.CLOSED}),
    InvocationLifecycle.PARTIAL: frozenset({InvocationLifecycle.CLOSED}),
    InvocationLifecycle.BLOCKED: frozenset({InvocationLifecycle.CLOSED}),
    InvocationLifecycle.TIMED_OUT: frozenset({InvocationLifecycle.CLOSED}),
    InvocationLifecycle.CANCELLED: frozenset({InvocationLifecycle.CLOSED}),
    InvocationLifecycle.CLOSED: frozenset(),
}


class LifecycleError(ValueError):
    """Raised when a Phase 4 invocation attempts an invalid transition."""


class ReplayLedgerError(ValueError):
    """Raised when the project-local idempotency ledger is unsafe or corrupt."""


def _ledger_path(request: CapabilityInvocationRequest, configured: str | Path | None) -> Path:
    workspace = Path(request.workspace)
    candidate = (
        Path(configured)
        if configured is not None
        else workspace / ".harness" / "phase4" / "invocation-ledger.json"
    )
    if not candidate.is_absolute():
        raise ReplayLedgerError("replay ledger must be absolute")
    try:
        target = validate_artifact_path(candidate, workspace)
        _mkdir_safe(target.parent, workspace)
    except ArtifactCaptureError as exc:
        raise ReplayLedgerError("replay ledger is outside the project workspace") from exc
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return target
    except OSError as exc:
        raise ReplayLedgerError("replay ledger cannot be inspected") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ReplayLedgerError("replay ledger is not a regular file")
    return target


def _load_ledger(path: Path) -> dict[str, dict[str, object]]:
    try:
        if not path.exists():
            return {}
        if path.stat().st_size > 128 * 1024:
            raise ReplayLedgerError("replay ledger exceeds its bound")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReplayLedgerError("replay ledger cannot be read safely") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != "P4-LEDGER-1":
        raise ReplayLedgerError("replay ledger schema is invalid")
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, Mapping):
        raise ReplayLedgerError("replay ledger entries are invalid")
    entries: dict[str, dict[str, object]] = {}
    for key, value in raw_entries.items():
        if not isinstance(key, str) or not isinstance(value, Mapping):
            raise ReplayLedgerError("replay ledger entry is invalid")
        idempotency_key = value.get("idempotency_key")
        request_digest = value.get("request_digest")
        if not isinstance(idempotency_key, str) or not isinstance(request_digest, str):
            raise ReplayLedgerError("replay ledger entry binding is invalid")
        entries[key] = dict(value)
    return entries


def _write_ledger(path: Path, entries: Mapping[str, Mapping[str, object]]) -> None:
    payload = {"schema_version": "P4-LEDGER-1", "entries": entries}
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    except OSError as exc:
        raise ReplayLedgerError("replay ledger could not be written atomically") from exc
    finally:
        if temporary_name is not None:
            with suppress(OSError):
                Path(temporary_name).unlink(missing_ok=True)


@contextmanager
def _ledger_lock(path: Path) -> Generator[None, None, None]:
    """Serialize reservations across threads and independent processes."""

    lock_path = path.with_name(f".{path.name}.lock")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise ReplayLedgerError("replay ledger lock is unsafe") from exc
    handle = os.fdopen(descriptor, "a+", encoding="utf-8")
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            with suppress(OSError):
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def transition(
    lifecycle: tuple[InvocationLifecycle, ...],
    next_state: InvocationLifecycle,
) -> tuple[InvocationLifecycle, ...]:
    if not lifecycle:
        if next_state is not InvocationLifecycle.DISCOVERED:
            raise LifecycleError("a lifecycle must begin at DISCOVERED")
        return (next_state,)
    current = lifecycle[-1]
    if next_state not in _TRANSITIONS[current]:
        raise LifecycleError(f"invalid lifecycle transition {current.value} -> {next_state.value}")
    return (*lifecycle, next_state)


def _empty_host_result(status: InvocationResultStatus, error_code: str) -> HostInvocationResult:
    now = int(time.time())
    return HostInvocationResult(
        status=status,
        thread_id=None,
        session_id=None,
        turn_id=None,
        host_version="phase4-policy",
        events=(),
        final_message=None,
        load_observation=HostLoadObservation.UNOBSERVABLE,
        invocation_observed=False,
        execution_observed=False,
        denied_approvals=0,
        cancellation_status="NOT_REQUESTED",
        error_code=error_code,
        started_at=now,
        completed_at=now,
    )


def _expected_invocation_id(
    *,
    task_id: str,
    run_id: str,
    capability_id: str,
    package_fingerprint: str,
    context_digest: str,
    mode: ExecutionMode,
) -> str:
    return (
        "INV-"
        + uuid.uuid5(
            uuid.NAMESPACE_URL,
            digest_payload(
                {
                    "task_id": task_id,
                    "run_id": run_id,
                    "capability": capability_id,
                    "fingerprint": package_fingerprint,
                    "context": context_digest,
                    "mode": mode,
                }
            ),
        ).hex[:24]
    )


class InvocationEngine:
    """Coordinate preflight, one bounded host request and evidence binding."""

    def __init__(
        self,
        adapter: CapabilityInvocationAdapter,
        *,
        clock: Callable[[], int] | None = None,
        replay_ledger: str | Path | None = None,
    ) -> None:
        self.adapter = adapter
        self._clock = clock or (lambda: int(time.time()))
        self._replay_ledger = Path(replay_ledger) if replay_ledger is not None else None
        self._used_real_invocations: set[str] = set()
        self._replay_lock = Lock()

    def prepare(
        self,
        record: CapabilityRecord,
        inventory: CapabilityInventory,
        resolution: ResolutionResult,
        policy: ExecutionPolicyRegistry,
        *,
        task_id: str,
        run_id: str,
        task: str,
        acceptance_criteria: tuple[str, ...],
        workspace: str | Path,
        mode: ExecutionMode,
        budget: Phase4Budget,
        expected_fingerprint: str | None = None,
        require_fingerprint_confirmation: bool = False,
    ) -> PreparedInvocation:
        preflight = build_preflight(
            record,
            inventory,
            resolution,
            policy,
            task_id=task_id,
            run_id=run_id,
            task=task,
            acceptance_criteria=acceptance_criteria,
            workspace=workspace,
            mode=mode,
            budget=budget,
            now=self._clock(),
        )
        if require_fingerprint_confirmation and expected_fingerprint is None:
            preflight = replace(
                preflight,
                allowed=False,
                blockers=(*preflight.blockers, "FINGERPRINT_CONFIRMATION_REQUIRED"),
                authorization=None,
                context=None,
                digest=preflight.digest,
            )
            preflight = replace(preflight, digest=preflight_digest(preflight))
        elif expected_fingerprint is not None and expected_fingerprint != record.content_hash:
            preflight = replace(
                preflight,
                allowed=False,
                blockers=(*preflight.blockers, "FINGERPRINT_CONFIRMATION_MISMATCH"),
                authorization=None,
                context=None,
                digest=preflight.digest,
            )
            preflight = replace(preflight, digest=preflight_digest(preflight))
        request: CapabilityInvocationRequest | None = None
        if (
            preflight.allowed
            and preflight.authorization is not None
            and preflight.context is not None
        ):
            types = preflight.authorization.artifact_policy.get("types", ())
            expected_artifacts = tuple(types) if isinstance(types, (tuple, list)) else ()
            invocation_id = _expected_invocation_id(
                task_id=task_id,
                run_id=run_id,
                capability_id=record.capability_id,
                package_fingerprint=record.content_hash,
                context_digest=preflight.context.digest,
                mode=mode,
            )
            request = CapabilityInvocationRequest(
                invocation_id=invocation_id,
                authorization=preflight.authorization,
                context=preflight.context,
                skill_name=record.capability_id,
                skill_path=preflight.context.skill_path,
                task=task,
                acceptance_criteria=acceptance_criteria,
                workspace=str(Path(workspace).resolve()),
                expected_artifacts=expected_artifacts,
                idempotency_key="IDEM-" + invocation_id.removeprefix("INV-"),
            )
        return PreparedInvocation(
            record=record,
            inventory=inventory,
            resolution=resolution,
            request=request,
            preflight=preflight,
            mode=mode,
            prepared_at=self._clock(),
        )

    def execute(
        self,
        record: CapabilityRecord,
        inventory: CapabilityInventory,
        resolution: ResolutionResult,
        policy: ExecutionPolicyRegistry,
        *,
        task_id: str,
        run_id: str,
        task: str,
        acceptance_criteria: tuple[str, ...],
        workspace: str | Path,
        mode: ExecutionMode,
        budget: Phase4Budget,
        expected_fingerprint: str | None = None,
        require_fingerprint_confirmation: bool = False,
    ) -> ExecutionOutcome:
        prepared = self.prepare(
            record,
            inventory,
            resolution,
            policy,
            task_id=task_id,
            run_id=run_id,
            task=task,
            acceptance_criteria=acceptance_criteria,
            workspace=workspace,
            mode=mode,
            budget=budget,
            expected_fingerprint=expected_fingerprint,
            require_fingerprint_confirmation=require_fingerprint_confirmation,
        )
        return self.execute_prepared(prepared)

    def execute_prepared(
        self,
        prepared: PreparedInvocation,
        *,
        cancel_event: Event | None = None,
    ) -> ExecutionOutcome:
        if not isinstance(prepared, PreparedInvocation):
            raise TypeError("prepared must be a PreparedInvocation")
        preflight = prepared.preflight
        binding_errors = self._prepared_binding_errors(prepared)
        if binding_errors:
            return self._blocked_outcome(prepared, binding_errors)
        if not preflight.allowed or prepared.request is None:
            return self._blocked_outcome(prepared, preflight.blockers)
        if prepared.mode is not ExecutionMode.CONTROLLED_REAL:
            return self._prepared_outcome(prepared)
        fresh, freshness_reason = revalidate_capability(prepared.record, Phase3Limits())
        if not fresh:
            return self._blocked_outcome(
                prepared,
                ("CAPABILITY_STALE_BEFORE_EXECUTION", freshness_reason),
            )
        authorization = prepared.request.authorization
        if self._clock() >= authorization.expires_at:
            return self._blocked_outcome(prepared, ("AUTHORIZATION_EXPIRED",))
        if cancel_event is not None and cancel_event.is_set():
            lifecycle = transition((InvocationLifecycle.DISCOVERED,), InvocationLifecycle.RESOLVED)
            lifecycle = transition(lifecycle, InvocationLifecycle.AUTHORIZED)
            lifecycle = transition(lifecycle, InvocationLifecycle.CONTEXT_PREPARED)
            lifecycle = transition(lifecycle, InvocationLifecycle.INVOCATION_REQUESTED)
            lifecycle = transition(lifecycle, InvocationLifecycle.CANCELLED)
            return self._host_terminal_outcome(
                prepared,
                _empty_host_result(
                    InvocationResultStatus.CANCELLED,
                    "CANCELLATION_REQUESTED_BEFORE_HOST_START",
                ),
                lifecycle,
            )
        try:
            preparation = self.adapter.prepare_invocation(prepared.request)
            host_errors = self.adapter.validate_invocation(prepared.request)
        except Exception:
            return self._blocked_outcome(prepared, ("HOST_PREPARATION_FAILURE",))
        if not _preparation_supported(preparation):
            return self._blocked_outcome(prepared, ("HOST_INVOCATION_UNSUPPORTED",))
        if host_errors:
            return self._blocked_outcome(prepared, tuple(host_errors))
        replay_error = self._reserve_replay(prepared.request)
        if replay_error is not None:
            return self._blocked_outcome(prepared, (replay_error,))
        lifecycle = transition((InvocationLifecycle.DISCOVERED,), InvocationLifecycle.RESOLVED)
        lifecycle = transition(lifecycle, InvocationLifecycle.AUTHORIZED)
        lifecycle = transition(lifecycle, InvocationLifecycle.CONTEXT_PREPARED)
        lifecycle = transition(lifecycle, InvocationLifecycle.INVOCATION_REQUESTED)
        try:
            host_result = self.adapter.request_invocation(
                prepared.request,
                budget=Phase4Budget(
                    timeout_seconds=authorization.timeout_seconds,
                    max_context_bytes=_mapping_int(authorization.context_budget, "max_bytes"),
                    max_host_events=_mapping_int(authorization.evidence_policy, "max_events"),
                    max_tool_calls=_mapping_int(authorization.iteration_budget, "tool_calls"),
                    max_repair_iterations=_mapping_int(
                        authorization.iteration_budget, "repair_iterations"
                    ),
                    max_verification_iterations=_mapping_int(
                        authorization.iteration_budget, "verification_iterations"
                    ),
                    max_artifacts=_mapping_int(authorization.artifact_policy, "max_count"),
                    max_evidence=_mapping_int(authorization.evidence_policy, "max_count"),
                    max_output_bytes=_mapping_int(
                        authorization.artifact_policy,
                        "max_bytes",
                        default=256 * 1024,
                    ),
                ),
                cancel_event=cancel_event or Event(),
            )
        except Exception:
            host_result = _empty_host_result(
                InvocationResultStatus.FAILURE,
                "HOST_ADAPTER_FAILURE",
            )
        try:
            host_result = self.adapter.observe_invocation(host_result)
            host_result = self.adapter.collect_result(host_result)
            if not isinstance(host_result, HostInvocationResult):
                raise TypeError("host adapter returned an invalid result")
        except Exception:
            host_result = _empty_host_result(
                InvocationResultStatus.FAILURE,
                "HOST_RESULT_OBSERVATION_FAILURE",
            )
        fresh_after_host, _freshness_reason = revalidate_capability(prepared.record, Phase3Limits())
        if not fresh_after_host:
            lifecycle = transition(lifecycle, InvocationLifecycle.FAILED)
            return self._host_failure_outcome(
                prepared,
                replace(
                    host_result,
                    status=InvocationResultStatus.FAILURE,
                    error_code="CAPABILITY_CHANGED_DURING_INVOCATION",
                ),
                lifecycle,
            )
        if not host_result.invocation_observed and host_result.status in {
            InvocationResultStatus.TIMED_OUT,
            InvocationResultStatus.CANCELLED,
        }:
            lifecycle = transition(
                lifecycle,
                InvocationLifecycle.TIMED_OUT
                if host_result.status is InvocationResultStatus.TIMED_OUT
                else InvocationLifecycle.CANCELLED,
            )
            return self._host_terminal_outcome(prepared, host_result, lifecycle)
        if host_result.invocation_observed:
            lifecycle = transition(lifecycle, InvocationLifecycle.HOST_ACKNOWLEDGED)
        else:
            lifecycle = transition(lifecycle, InvocationLifecycle.FAILED)
            return self._host_failure_outcome(prepared, host_result, lifecycle)
        if host_result.status in {
            InvocationResultStatus.TIMED_OUT,
            InvocationResultStatus.CANCELLED,
        }:
            lifecycle = transition(
                lifecycle,
                InvocationLifecycle.TIMED_OUT
                if host_result.status is InvocationResultStatus.TIMED_OUT
                else InvocationLifecycle.CANCELLED,
            )
            return self._host_terminal_outcome(prepared, host_result, lifecycle)
        lifecycle = transition(lifecycle, InvocationLifecycle.EXECUTING)
        lifecycle = transition(lifecycle, InvocationLifecycle.RESULT_RECEIVED)
        lifecycle = transition(lifecycle, InvocationLifecycle.VERIFYING)
        if not host_result.execution_observed:
            lifecycle = transition(lifecycle, InvocationLifecycle.FAILED)
            return self._host_failure_outcome(
                prepared,
                replace(
                    host_result,
                    status=InvocationResultStatus.FAILURE,
                    error_code="HOST_EXECUTION_UNOBSERVED",
                ),
                lifecycle,
            )
        artifacts = self._capture_artifacts(prepared.request, host_result, authorization)
        verification = verify_host_result(
            prepared.request,
            host_result,
            artifacts,
            evidence_refs=(f"receipt://{prepared.request.invocation_id}",),
        )
        if (
            verification.status == "VERIFIED"
            and host_result.status is InvocationResultStatus.SUCCESS
        ):
            lifecycle = transition(lifecycle, InvocationLifecycle.VERIFIED)
            status = InvocationResultStatus.SUCCESS
        elif host_result.status is InvocationResultStatus.PARTIAL:
            lifecycle = transition(lifecycle, InvocationLifecycle.PARTIAL)
            status = InvocationResultStatus.PARTIAL
        else:
            lifecycle = transition(lifecycle, InvocationLifecycle.FAILED)
            status = InvocationResultStatus.FAILURE
        lifecycle = transition(lifecycle, InvocationLifecycle.CLOSED)
        assurance = self._assurance(host_result, verification, status)
        receipt = self._receipt(
            prepared,
            status=status,
            lifecycle=lifecycle,
            host_result=host_result,
            artifacts=artifacts,
            verification=verification,
        )
        receipt_errors = validate_receipt_binding(
            receipt,
            prepared.request,
            host_result,
            artifacts,
            verification,
            expected_status=status,
        )
        if receipt_errors:
            failed_checks = (*verification.checks, "RECEIPT_BINDING_FAILED")
            failed_reason = "; ".join(receipt_errors)
            verification = replace(
                verification,
                status="FAILED",
                checks=failed_checks,
                reason=failed_reason,
                digest=digest_payload(
                    {
                        "status": "FAILED",
                        "acceptance_criteria": verification.acceptance_criteria,
                        "artifact_refs": verification.artifact_refs,
                        "evidence_refs": verification.evidence_refs,
                        "checks": failed_checks,
                        "reason": failed_reason,
                        "request_digest": verification.request_digest,
                        "host_executable_digest": verification.host_executable_digest,
                        "host_interpreter_digest": verification.host_interpreter_digest,
                    }
                ),
            )
            status = InvocationResultStatus.FAILURE
            if lifecycle[-1] is InvocationLifecycle.CLOSED:
                lifecycle = lifecycle[:-1]
            verifying_index = lifecycle.index(InvocationLifecycle.VERIFYING)
            lifecycle = lifecycle[: verifying_index + 1]
            lifecycle = transition(lifecycle, InvocationLifecycle.FAILED)
            lifecycle = transition(lifecycle, InvocationLifecycle.CLOSED)
            assurance = self._assurance(host_result, verification, status)
            receipt = self._receipt(
                prepared,
                status=status,
                lifecycle=lifecycle,
                host_result=host_result,
                artifacts=artifacts,
                verification=verification,
            )
            if validate_receipt_binding(
                receipt,
                prepared.request,
                host_result,
                artifacts,
                verification,
                expected_status=status,
            ):
                raise RuntimeError("receipt binding remained invalid after fail-closed repair")
        limitations = assurance.limitations if assurance is not None else ()
        return ExecutionOutcome(
            mode=prepared.mode,
            status=status,
            blockers=(),
            warnings=preflight.warnings,
            host_invoked=True,
            preflight=preflight,
            receipt=receipt,
            artifacts=artifacts,
            verification=verification,
            assurance=assurance,
            host_result=host_result,
            limitations=limitations,
        )

    @staticmethod
    def _prepared_binding_errors(prepared: PreparedInvocation) -> tuple[str, ...]:
        errors: list[str] = []
        preflight = prepared.preflight
        if prepared.mode is not preflight.mode:
            errors.append("PREPARED_MODE_MISMATCH")
        try:
            if preflight_digest(preflight) != preflight.digest:
                errors.append("PREFLIGHT_DIGEST_MISMATCH")
        except (TypeError, ValueError, OSError):
            errors.append("PREFLIGHT_BINDING_INVALID")
        if not preflight.allowed:
            return tuple(dict.fromkeys(errors))
        request = prepared.request
        authorization = preflight.authorization
        context = preflight.context
        if request is None or authorization is None or context is None:
            errors.append("PREPARED_AUTHORIZATION_MISSING")
            return tuple(dict.fromkeys(errors))
        if request.authorization != authorization:
            errors.append("REQUEST_AUTHORIZATION_MISMATCH")
        if request.context != context:
            errors.append("REQUEST_CONTEXT_MISMATCH")
        if authorization.requested_execution_mode is not prepared.mode:
            errors.append("AUTHORIZED_MODE_MISMATCH")
        if authorization.task_id != context.task_id:
            errors.append("AUTHORIZATION_CONTEXT_TASK_MISMATCH")
        if authorization.capability_id != prepared.record.capability_id:
            errors.append("AUTHORIZED_CAPABILITY_MISMATCH")
        if authorization.scope != prepared.record.scope:
            errors.append("AUTHORIZED_SCOPE_MISMATCH")
        authorized_host_digest = authorization.filesystem_policy.get("host_executable_digest")
        if authorization.host_executable_digest != authorized_host_digest:
            errors.append("AUTHORIZED_HOST_EXECUTABLE_MISMATCH")
        authorized_interpreter_digest = authorization.filesystem_policy.get(
            "host_interpreter_digest"
        )
        if authorization.host_interpreter_digest != authorized_interpreter_digest:
            errors.append("AUTHORIZED_HOST_INTERPRETER_MISMATCH")
        if (
            prepared.mode is ExecutionMode.CONTROLLED_REAL
            and authorization.host_executable_digest is None
        ):
            errors.append("AUTHORIZED_HOST_EXECUTABLE_MISSING")
        if (
            prepared.mode is ExecutionMode.CONTROLLED_REAL
            and authorization.host_interpreter_digest is None
        ):
            errors.append("AUTHORIZED_HOST_INTERPRETER_MISSING")
        if authorization.capability_version != prepared.record.version:
            errors.append("AUTHORIZED_VERSION_MISMATCH")
        if authorization.package_fingerprint != prepared.record.content_hash:
            errors.append("AUTHORIZED_FINGERPRINT_MISMATCH")
        if context.capability_id != prepared.record.capability_id:
            errors.append("CONTEXT_CAPABILITY_MISMATCH")
        if context.package_fingerprint != prepared.record.content_hash:
            errors.append("CONTEXT_FINGERPRINT_MISMATCH")
        if context.task_digest != digest_payload(request.task):
            errors.append("REQUEST_TASK_DIGEST_MISMATCH")
        if context.acceptance_criteria != request.acceptance_criteria:
            errors.append("REQUEST_ACCEPTANCE_CRITERIA_MISMATCH")
        if context.skill_path != request.skill_path:
            errors.append("REQUEST_SKILL_PATH_MISMATCH")
        authorized_workspace = authorization.filesystem_policy.get("workspace")
        if not isinstance(authorized_workspace, str) or not authorized_workspace:
            errors.append("AUTHORIZED_WORKSPACE_MISSING")
        else:
            try:
                if Path(request.workspace).resolve() != Path(authorized_workspace).resolve():
                    errors.append("REQUEST_WORKSPACE_MISMATCH")
            except (OSError, RuntimeError):
                errors.append("REQUEST_WORKSPACE_INVALID")
        authorized_types = authorization.artifact_policy.get("types")
        if (
            isinstance(authorized_types, (tuple, list))
            and tuple(authorized_types) != request.expected_artifacts
        ):
            errors.append("REQUEST_ARTIFACT_POLICY_MISMATCH")
        expected_invocation = _expected_invocation_id(
            task_id=authorization.task_id,
            run_id=authorization.run_id,
            capability_id=prepared.record.capability_id,
            package_fingerprint=prepared.record.content_hash,
            context_digest=context.digest,
            mode=prepared.mode,
        )
        if request.invocation_id != expected_invocation:
            errors.append("INVOCATION_ID_BINDING_MISMATCH")
        if request.idempotency_key != f"IDEM-{expected_invocation.removeprefix('INV-')}":
            errors.append("IDEMPOTENCY_KEY_BINDING_MISMATCH")
        record_identity = (
            prepared.record.capability_id,
            prepared.record.version,
            prepared.record.content_hash,
            prepared.record.root_id,
            prepared.record.path,
        )
        if record_identity not in {
            (
                item.capability_id,
                item.version,
                item.content_hash,
                item.root_id,
                item.path,
            )
            for item in prepared.inventory.capabilities
        }:
            errors.append("INVENTORY_RECORD_BINDING_MISMATCH")
        if record_identity not in {
            (
                item.capability_id,
                item.version,
                item.content_hash,
                item.root_id,
                item.path,
            )
            for item in prepared.resolution.selected
        }:
            errors.append("RESOLUTION_RECORD_BINDING_MISMATCH")
        return tuple(dict.fromkeys(errors))

    def _reserve_replay(self, request: CapabilityInvocationRequest) -> str | None:
        try:
            path = _ledger_path(request, self._replay_ledger)
            request_digest = stable_digest_payload(request, workspace=request.workspace)
            with self._replay_lock:
                if request.invocation_id in self._used_real_invocations:
                    return "REPLAY_DETECTED"
                with _ledger_lock(path):
                    entries = _load_ledger(path)
                    existing = entries.get(request.invocation_id)
                    if existing is not None:
                        if existing.get("request_digest") == request_digest:
                            return "REPLAY_DETECTED"
                        return "IDEMPOTENCY_KEY_REUSE"
                    for entry in entries.values():
                        if entry.get("idempotency_key") == request.idempotency_key:
                            return "REPLAY_DETECTED"
                    entries[request.invocation_id] = {
                        "idempotency_key": request.idempotency_key,
                        "request_digest": request_digest,
                        "reserved_at": self._clock(),
                        "status": "RESERVED_FOR_CONTROLLED_REAL",
                    }
                    _write_ledger(path, entries)
                self._used_real_invocations.add(request.invocation_id)
        except ReplayLedgerError as exc:
            return str(exc) if str(exc) else "REPLAY_LEDGER_INVALID"
        return None

    def _capture_artifacts(
        self,
        request: CapabilityInvocationRequest,
        result: HostInvocationResult,
        authorization: CapabilityExecutionAuthorization,
    ) -> tuple[ArtifactRecord, ...]:
        if result.final_message is None:
            return ()
        try:
            artifact = capture_host_response(
                request,
                result,
                timestamp=self._clock(),
                max_bytes=_mapping_int(
                    authorization.artifact_policy,
                    "max_bytes",
                    default=256 * 1024,
                ),
            )
        except ArtifactCaptureError:
            return ()
        return (artifact,) if artifact is not None else ()

    def _assurance(
        self,
        host_result: HostInvocationResult,
        verification: VerificationResult,
        status: InvocationResultStatus,
    ) -> AssuranceResult:
        limitations: list[str] = []
        if host_result.load_observation in {
            HostLoadObservation.UNOBSERVABLE,
            HostLoadObservation.PARTIAL,
            HostLoadObservation.UNSUPPORTED,
        }:
            limitations.append(host_result.load_observation.value)
        if host_result.denied_approvals:
            limitations.append("HOST_APPROVALS_DENIED_BY_POLICY")
        if status is InvocationResultStatus.SUCCESS and verification.status == "VERIFIED":
            decision = (
                AssuranceDecision.PASS_WITH_LIMITATIONS if limitations else AssuranceDecision.PASS
            )
            reason = "bounded result is verified; host limitations remain explicit"
        elif status is InvocationResultStatus.BLOCKED:
            decision = AssuranceDecision.BLOCK
            reason = "policy or host boundary blocked the invocation"
        else:
            decision = AssuranceDecision.STOP
            reason = "result did not satisfy the bounded verification chain"
        return AssuranceResult(decision, reason, tuple(limitations), verification.digest)

    def _blocked_outcome(
        self,
        prepared: PreparedInvocation,
        blockers: tuple[str, ...],
    ) -> ExecutionOutcome:
        unique = tuple(dict.fromkeys((*prepared.preflight.blockers, *blockers)))
        lifecycle = transition((InvocationLifecycle.DISCOVERED,), InvocationLifecycle.BLOCKED)
        lifecycle = transition(lifecycle, InvocationLifecycle.CLOSED)
        host_result = _empty_host_result(
            InvocationResultStatus.BLOCKED, unique[0] if unique else "BLOCKED"
        )
        receipt = self._receipt(
            prepared,
            status=InvocationResultStatus.BLOCKED,
            lifecycle=lifecycle,
            host_result=host_result,
            artifacts=(),
            verification=None,
        )
        return ExecutionOutcome(
            mode=prepared.mode,
            status=InvocationResultStatus.BLOCKED,
            blockers=unique,
            warnings=prepared.preflight.warnings,
            host_invoked=False,
            preflight=prepared.preflight,
            receipt=receipt,
            artifacts=(),
            verification=None,
            assurance=AssuranceResult(
                AssuranceDecision.BLOCK,
                "preflight blocked the invocation",
                unique,
                None,
            ),
            host_result=host_result,
            limitations=unique,
        )

    def _prepared_outcome(self, prepared: PreparedInvocation) -> ExecutionOutcome:
        lifecycle = transition((InvocationLifecycle.DISCOVERED,), InvocationLifecycle.RESOLVED)
        lifecycle = transition(lifecycle, InvocationLifecycle.AUTHORIZED)
        lifecycle = transition(lifecycle, InvocationLifecycle.CONTEXT_PREPARED)
        lifecycle = transition(lifecycle, InvocationLifecycle.CLOSED)
        host_result = _empty_host_result(InvocationResultStatus.PREPARED, "NO_HOST_INVOCATION")
        receipt = self._receipt(
            prepared,
            status=InvocationResultStatus.PREPARED,
            lifecycle=lifecycle,
            host_result=host_result,
            artifacts=(),
            verification=None,
        )
        return ExecutionOutcome(
            mode=prepared.mode,
            status=InvocationResultStatus.PREPARED,
            blockers=(),
            warnings=prepared.preflight.warnings,
            host_invoked=False,
            preflight=prepared.preflight,
            receipt=receipt,
            artifacts=(),
            verification=None,
            assurance=None,
            host_result=host_result,
            limitations=("NO_HOST_INVOCATION",),
        )

    def _host_failure_outcome(
        self,
        prepared: PreparedInvocation,
        host_result: HostInvocationResult,
        lifecycle: tuple[InvocationLifecycle, ...],
    ) -> ExecutionOutcome:
        closed = transition(lifecycle, InvocationLifecycle.CLOSED)
        receipt = self._receipt(
            prepared,
            status=host_result.status,
            lifecycle=closed,
            host_result=host_result,
            artifacts=(),
            verification=None,
        )
        return ExecutionOutcome(
            mode=prepared.mode,
            status=host_result.status,
            blockers=(host_result.error_code or "HOST_INVOCATION_FAILED",),
            warnings=prepared.preflight.warnings,
            host_invoked=host_result.invocation_observed,
            preflight=prepared.preflight,
            receipt=receipt,
            artifacts=(),
            verification=None,
            assurance=AssuranceResult(
                AssuranceDecision.STOP,
                "host did not provide an acknowledged executable turn",
                (host_result.error_code or "HOST_INVOCATION_FAILED",),
                None,
            ),
            host_result=host_result,
            limitations=(host_result.error_code or "HOST_INVOCATION_FAILED",),
        )

    def _host_terminal_outcome(
        self,
        prepared: PreparedInvocation,
        host_result: HostInvocationResult,
        lifecycle: tuple[InvocationLifecycle, ...],
    ) -> ExecutionOutcome:
        closed = transition(lifecycle, InvocationLifecycle.CLOSED)
        error = host_result.error_code or host_result.status.value
        receipt = self._receipt(
            prepared,
            status=host_result.status,
            lifecycle=closed,
            host_result=host_result,
            artifacts=(),
            verification=None,
        )
        return ExecutionOutcome(
            mode=prepared.mode,
            status=host_result.status,
            blockers=(error,),
            warnings=prepared.preflight.warnings,
            host_invoked=host_result.invocation_observed,
            preflight=prepared.preflight,
            receipt=receipt,
            artifacts=(),
            verification=None,
            assurance=AssuranceResult(AssuranceDecision.STOP, error, (error,), None),
            host_result=host_result,
            limitations=(error,),
        )

    def _receipt(
        self,
        prepared: PreparedInvocation,
        *,
        status: InvocationResultStatus,
        lifecycle: tuple[InvocationLifecycle, ...],
        host_result: HostInvocationResult,
        artifacts: tuple[ArtifactRecord, ...],
        verification: VerificationResult | None,
    ) -> InvocationReceipt:
        request = prepared.request
        invocation_id = (
            request.invocation_id
            if request is not None
            else "INV-BLOCKED-" + prepared.preflight.digest.removeprefix("sha256:")[:24]
        )
        authorization = request.authorization if request is not None else None
        context = request.context if request is not None else None
        created_at = prepared.prepared_at
        closed_at = self._clock()
        if closed_at < created_at:
            closed_at = created_at
        authorization_id = authorization.authorization_id if authorization else None
        authorization_digest = (
            stable_digest_payload(authorization, workspace=request.workspace)
            if authorization and request is not None
            else None
        )
        context_digest = context.digest if context else None
        request_digest = (
            stable_digest_payload(request, workspace=request.workspace)
            if request is not None
            else None
        )
        host_event_digest = digest_payload(host_result.events)
        result_digest = digest_payload(host_result)
        host_executable_path = host_result.host_executable_path
        host_executable_digest = host_result.host_executable_digest
        host_command = host_result.host_command
        host_interpreter_path = host_result.host_interpreter_path
        host_interpreter_digest = host_result.host_interpreter_digest
        artifact_refs = tuple(item.artifact_id for item in artifacts)
        verification_refs = (verification.digest,) if verification is not None else ()
        material = {
            "invocation_id": invocation_id,
            "mode": prepared.mode,
            "status": status,
            "capability_id": prepared.record.capability_id,
            "capability_version": prepared.record.version,
            "package_fingerprint": prepared.record.content_hash,
            "authorization_id": authorization_id,
            "authorization_digest": authorization_digest,
            "context_digest": context_digest,
            "request_digest": request_digest,
            "lifecycle": lifecycle,
            "host_invoked": host_result.invocation_observed,
            "host_load_observation": host_result.load_observation,
            "host_event_count": len(host_result.events),
            "host_event_digest": host_event_digest,
            "result_digest": result_digest,
            "host_executable_path": host_executable_path,
            "host_executable_digest": host_executable_digest,
            "host_command": host_command,
            "host_interpreter_path": host_interpreter_path,
            "host_interpreter_digest": host_interpreter_digest,
            "artifact_refs": artifact_refs,
            "verification_refs": verification_refs,
            "created_at": created_at,
            "closed_at": closed_at,
        }
        receipt = InvocationReceipt(
            invocation_id=invocation_id,
            mode=prepared.mode,
            status=status,
            capability_id=prepared.record.capability_id,
            capability_version=prepared.record.version,
            package_fingerprint=prepared.record.content_hash,
            authorization_id=authorization_id,
            authorization_digest=authorization_digest,
            context_digest=context_digest,
            request_digest=request_digest,
            lifecycle=lifecycle,
            host_invoked=host_result.invocation_observed,
            host_load_observation=host_result.load_observation,
            host_event_count=len(host_result.events),
            host_event_digest=host_event_digest,
            result_digest=result_digest,
            host_executable_path=host_executable_path,
            host_executable_digest=host_executable_digest,
            host_command=host_command,
            host_interpreter_path=host_interpreter_path,
            host_interpreter_digest=host_interpreter_digest,
            artifact_refs=artifact_refs,
            verification_refs=verification_refs,
            created_at=created_at,
            closed_at=closed_at,
            receipt_digest=digest_payload(material),
        )
        if invocation_receipt_digest(receipt) != receipt.receipt_digest:
            raise RuntimeError("receipt digest construction mismatch")
        return receipt


def _preparation_supported(preparation: object) -> bool:
    if isinstance(preparation, dict):
        return bool(preparation.get("supported", False))
    return bool(getattr(preparation, "supported", False))


def _mapping_int(mapping: object, key: str, default: int = 0) -> int:
    if isinstance(mapping, Mapping):
        value = mapping.get(key)
        return (
            value
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            else default
        )
    return default
