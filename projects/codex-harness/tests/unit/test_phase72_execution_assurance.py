from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from test_phase4_execution import FakeHost, _fixture

from harness_kernel.phase4_execution import InvocationEngine
from harness_kernel.phase4_models import ExecutionMode, InvocationResultStatus, Phase4Budget
from harness_kernel.phase4_policy import preflight_digest

PreparedMutation = Callable[[object], None]


def _prepared(tmp_path: Path):
    record, inventory, resolution, policy = _fixture(tmp_path)
    host = FakeHost()
    engine = InvocationEngine(host)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P7.2-BINDING",
        run_id="RUN-P7.2-BINDING",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert prepared.request is not None
    assert prepared.preflight.authorization is not None
    assert prepared.preflight.context is not None
    return engine, host, prepared


def _refresh_preflight(prepared: object) -> None:
    object.__setattr__(
        prepared.preflight,
        "digest",
        preflight_digest(prepared.preflight),
    )


def _replace_authorization(prepared: object, **changes: object) -> None:
    authorization = replace(prepared.preflight.authorization, **changes)
    object.__setattr__(prepared.preflight, "authorization", authorization)
    object.__setattr__(prepared.request, "authorization", authorization)
    _refresh_preflight(prepared)


def _replace_context(prepared: object, **changes: object) -> None:
    context = replace(prepared.preflight.context, **changes)
    object.__setattr__(prepared.preflight, "context", context)
    object.__setattr__(prepared.request, "context", context)
    _refresh_preflight(prepared)


def _request_authorization_mismatch(prepared: object) -> None:
    object.__setattr__(
        prepared.request,
        "authorization",
        replace(prepared.request.authorization, scope="GLOBAL"),
    )


def _request_context_mismatch(prepared: object) -> None:
    object.__setattr__(
        prepared.request,
        "context",
        replace(prepared.request.context, task_id="TASK-TAMPERED"),
    )


def _prepared_mode_mismatch(prepared: object) -> None:
    object.__setattr__(prepared, "mode", ExecutionMode.PREPARE_ONLY)


def _preflight_digest_mismatch(prepared: object) -> None:
    object.__setattr__(prepared.preflight, "digest", "sha256:" + "f" * 64)


def _request_missing(prepared: object) -> None:
    object.__setattr__(prepared, "request", None)


def _authorization_context_task_mismatch(prepared: object) -> None:
    _replace_authorization(prepared, task_id="TASK-TAMPERED")


def _authorized_capability_mismatch(prepared: object) -> None:
    _replace_authorization(prepared, capability_id="other-capability")


def _authorized_scope_mismatch(prepared: object) -> None:
    _replace_authorization(prepared, scope="GLOBAL")


def _authorized_executable_mismatch(prepared: object) -> None:
    _replace_authorization(
        prepared,
        host_executable_digest="sha256:" + "c" * 64,
    )


def _authorized_interpreter_mismatch(prepared: object) -> None:
    _replace_authorization(
        prepared,
        host_interpreter_digest="sha256:" + "c" * 64,
    )


def _authorized_executable_missing(prepared: object) -> None:
    policy = {
        **prepared.preflight.authorization.filesystem_policy,
        "host_executable_digest": None,
    }
    _replace_authorization(
        prepared,
        filesystem_policy=policy,
        host_executable_digest=None,
    )


def _authorized_interpreter_missing(prepared: object) -> None:
    policy = {
        **prepared.preflight.authorization.filesystem_policy,
        "host_interpreter_digest": None,
    }
    _replace_authorization(
        prepared,
        filesystem_policy=policy,
        host_interpreter_digest=None,
    )


def _authorized_version_mismatch(prepared: object) -> None:
    _replace_authorization(prepared, capability_version="9.9.9")


def _authorized_fingerprint_mismatch(prepared: object) -> None:
    _replace_authorization(prepared, package_fingerprint="sha256:" + "c" * 64)


def _context_capability_mismatch(prepared: object) -> None:
    _replace_context(prepared, capability_id="other-capability")


def _context_fingerprint_mismatch(prepared: object) -> None:
    _replace_context(prepared, package_fingerprint="sha256:" + "c" * 64)


def _request_task_digest_mismatch(prepared: object) -> None:
    object.__setattr__(prepared.request, "task", "tampered task")


def _request_acceptance_mismatch(prepared: object) -> None:
    object.__setattr__(prepared.request, "acceptance_criteria", ("tampered",))


def _request_skill_path_mismatch(prepared: object) -> None:
    object.__setattr__(
        prepared.request,
        "skill_path",
        str(Path(prepared.request.skill_path).with_name("other-SKILL.md")),
    )


def _authorized_workspace_missing(prepared: object) -> None:
    policy = {
        **prepared.preflight.authorization.filesystem_policy,
        "workspace": None,
    }
    _replace_authorization(prepared, filesystem_policy=policy)


def _request_workspace_mismatch(prepared: object) -> None:
    object.__setattr__(prepared.request, "workspace", str(Path("/tmp/other-workspace")))


def _request_workspace_invalid(prepared: object) -> None:
    object.__setattr__(prepared.request, "workspace", "\x00")


def _request_artifact_policy_mismatch(prepared: object) -> None:
    object.__setattr__(prepared.request, "expected_artifacts", ("UNAUTHORIZED",))


def _invocation_id_mismatch(prepared: object) -> None:
    object.__setattr__(prepared.request, "invocation_id", "INV-TAMPERED")


def _idempotency_key_mismatch(prepared: object) -> None:
    object.__setattr__(prepared.request, "idempotency_key", "IDEM-TAMPERED")


def _inventory_record_mismatch(prepared: object) -> None:
    capabilities = tuple(
        item for item in prepared.inventory.capabilities if item is not prepared.record
    )
    object.__setattr__(
        prepared,
        "inventory",
        replace(prepared.inventory, capabilities=capabilities),
    )


def _resolution_record_mismatch(prepared: object) -> None:
    object.__setattr__(prepared, "resolution", replace(prepared.resolution, selected=()))


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        pytest.param(_prepared_mode_mismatch, "PREPARED_MODE_MISMATCH", id="mode"),
        pytest.param(
            _preflight_digest_mismatch,
            "PREFLIGHT_DIGEST_MISMATCH",
            id="preflight-digest",
        ),
        pytest.param(
            _request_missing,
            "PREPARED_AUTHORIZATION_MISSING",
            id="request-missing",
        ),
        pytest.param(
            _request_authorization_mismatch,
            "REQUEST_AUTHORIZATION_MISMATCH",
            id="request-authorization",
        ),
        pytest.param(
            _request_context_mismatch,
            "REQUEST_CONTEXT_MISMATCH",
            id="request-context",
        ),
        pytest.param(
            _authorization_context_task_mismatch,
            "AUTHORIZATION_CONTEXT_TASK_MISMATCH",
            id="authorization-context-task",
        ),
        pytest.param(
            _authorized_capability_mismatch,
            "AUTHORIZED_CAPABILITY_MISMATCH",
            id="authorized-capability",
        ),
        pytest.param(_authorized_scope_mismatch, "AUTHORIZED_SCOPE_MISMATCH", id="scope"),
        pytest.param(
            _authorized_executable_mismatch,
            "AUTHORIZED_HOST_EXECUTABLE_MISMATCH",
            id="executable-binding",
        ),
        pytest.param(
            _authorized_interpreter_mismatch,
            "AUTHORIZED_HOST_INTERPRETER_MISMATCH",
            id="interpreter-binding",
        ),
        pytest.param(
            _authorized_executable_missing,
            "AUTHORIZED_HOST_EXECUTABLE_MISSING",
            id="executable-missing",
        ),
        pytest.param(
            _authorized_interpreter_missing,
            "AUTHORIZED_HOST_INTERPRETER_MISSING",
            id="interpreter-missing",
        ),
        pytest.param(
            _authorized_version_mismatch,
            "AUTHORIZED_VERSION_MISMATCH",
            id="version",
        ),
        pytest.param(
            _authorized_fingerprint_mismatch,
            "AUTHORIZED_FINGERPRINT_MISMATCH",
            id="fingerprint",
        ),
        pytest.param(
            _context_capability_mismatch,
            "CONTEXT_CAPABILITY_MISMATCH",
            id="context-capability",
        ),
        pytest.param(
            _context_fingerprint_mismatch,
            "CONTEXT_FINGERPRINT_MISMATCH",
            id="context-fingerprint",
        ),
        pytest.param(
            _request_task_digest_mismatch,
            "REQUEST_TASK_DIGEST_MISMATCH",
            id="task-digest",
        ),
        pytest.param(
            _request_acceptance_mismatch,
            "REQUEST_ACCEPTANCE_CRITERIA_MISMATCH",
            id="acceptance",
        ),
        pytest.param(
            _request_skill_path_mismatch,
            "REQUEST_SKILL_PATH_MISMATCH",
            id="skill-path",
        ),
        pytest.param(
            _authorized_workspace_missing,
            "AUTHORIZED_WORKSPACE_MISSING",
            id="workspace-missing",
        ),
        pytest.param(
            _request_workspace_mismatch,
            "REQUEST_WORKSPACE_MISMATCH",
            id="workspace-mismatch",
        ),
        pytest.param(
            _request_workspace_invalid,
            "REQUEST_WORKSPACE_INVALID",
            id="workspace-invalid",
        ),
        pytest.param(
            _request_artifact_policy_mismatch,
            "REQUEST_ARTIFACT_POLICY_MISMATCH",
            id="artifact-policy",
        ),
        pytest.param(
            _invocation_id_mismatch,
            "INVOCATION_ID_BINDING_MISMATCH",
            id="invocation-id",
        ),
        pytest.param(
            _idempotency_key_mismatch,
            "IDEMPOTENCY_KEY_BINDING_MISMATCH",
            id="idempotency-key",
        ),
        pytest.param(
            _inventory_record_mismatch,
            "INVENTORY_RECORD_BINDING_MISMATCH",
            id="inventory-record",
        ),
        pytest.param(
            _resolution_record_mismatch,
            "RESOLUTION_RECORD_BINDING_MISMATCH",
            id="resolution-record",
        ),
    ),
)
def test_prepared_binding_tampering_blocks_without_host_or_persistence(
    tmp_path: Path,
    mutation: PreparedMutation,
    expected: str,
) -> None:
    engine, host, prepared = _prepared(tmp_path)
    mutation(prepared)

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.BLOCKED
    assert expected in outcome.blockers
    assert outcome.host_invoked is False
    assert host.calls == 0
    assert not (tmp_path / ".harness").exists()
