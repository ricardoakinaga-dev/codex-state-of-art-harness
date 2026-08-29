from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event

import pytest

from harness_kernel.phase3_host import CodexHostAdapter
from harness_kernel.phase3_resolution import ResolutionEngine
from harness_kernel.phase4_execution import InvocationEngine, LifecycleError, transition
from harness_kernel.phase4_models import (
    ExecutionMode,
    HostInvocationResult,
    HostLoadObservation,
    InvocationLifecycle,
    InvocationResultStatus,
    Phase4Budget,
    public_data,
    stable_digest_payload,
)
from harness_kernel.phase4_policy import ExecutionPolicyRegistry, PilotRule


def _fixture(tmp_path: Path):
    package = tmp_path / ".agents" / "skills" / "safe-pilot"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: safe-pilot\nversion: 0.1.0\n---\n"
        "Return PHASE4_SAFE_PILOT_ARTIFACT and do not use tools.\n",
        encoding="utf-8",
    )
    adapter = CodexHostAdapter(
        project_root=tmp_path,
        home_dir=tmp_path / "no-home",
        codex_home=tmp_path / "no-codex-home",
    )
    inventory = adapter.discover_capabilities()
    record = next(item for item in inventory.capabilities if item.capability_id == "safe-pilot")
    resolution = ResolutionEngine().resolve(inventory, "safe-pilot")
    policy = ExecutionPolicyRegistry(
        (
            PilotRule(
                capability_id=record.capability_id,
                version=record.version,
                package_fingerprint=record.content_hash,
                host_executable_digest="sha256:" + "a" * 64,
                host_interpreter_digest="sha256:" + "b" * 64,
                execution_approved=True,
                allowed_modes=(
                    ExecutionMode.DRY_RUN,
                    ExecutionMode.PREPARE_ONLY,
                    ExecutionMode.CONTROLLED_REAL,
                ),
                reason="script-free fixture",
            ),
        )
    )
    return record, inventory, resolution, policy


@dataclass
class FakeHost:
    calls: int = 0
    result: HostInvocationResult | None = None

    def prepare_invocation(self, request):
        return {"supported": True, "reason": "fake"}

    def validate_invocation(self, request):
        return ()

    def request_invocation(self, request, *, budget, cancel_event=None):
        self.calls += 1
        assert cancel_event is not None
        return self.result or HostInvocationResult(
            status=InvocationResultStatus.SUCCESS,
            thread_id="thread-1",
            session_id="session-1",
            turn_id="turn-1",
            host_version="fake",
            events=(),
            final_message="PHASE4_SAFE_PILOT_ARTIFACT",
            load_observation=HostLoadObservation.UNOBSERVABLE,
            invocation_observed=True,
            execution_observed=True,
            denied_approvals=0,
            cancellation_status="NOT_REQUESTED",
            error_code=None,
            started_at=1_700_000_000,
            completed_at=1_700_000_001,
            host_executable_path="/bin/codex-test",
            host_executable_digest="sha256:" + "a" * 64,
            host_command=("/bin/node-test", "/bin/codex-test"),
            host_interpreter_path="/bin/node-test",
            host_interpreter_digest="sha256:" + "b" * 64,
        )

    def observe_invocation(self, result):
        return result

    def cancel_invocation(self, request):
        return "NOT_ACTIVE"

    def collect_result(self, result):
        return result


def test_dry_run_and_prepare_only_never_call_host(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    host = FakeHost()
    engine = InvocationEngine(host)

    for mode in (ExecutionMode.DRY_RUN, ExecutionMode.PREPARE_ONLY):
        prepared = engine.prepare(
            record,
            inventory,
            resolution,
            policy,
            task_id=f"TASK-{mode.value}",
            run_id=f"RUN-{mode.value}",
            task="Return a bounded response.",
            acceptance_criteria=("response is non-empty",),
            workspace=tmp_path,
            mode=mode,
            budget=Phase4Budget(),
        )
        outcome = engine.execute_prepared(prepared)
        assert outcome.mode is mode
        assert outcome.status is InvocationResultStatus.PREPARED
    assert host.calls == 0


def test_controlled_real_captures_and_verifies_host_response(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    host = FakeHost()
    engine = InvocationEngine(host)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-REAL",
        run_id="RUN-P4-REAL",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )

    outcome = engine.execute_prepared(prepared)

    assert host.calls == 1
    assert outcome.status is InvocationResultStatus.SUCCESS
    assert outcome.verification is not None
    assert outcome.verification.status == "VERIFIED"
    assert outcome.assurance is not None
    assert outcome.assurance.decision.value == "PASS_WITH_LIMITATIONS"
    assert outcome.artifacts
    assert Path(outcome.artifacts[0].location).is_relative_to(tmp_path)
    assert outcome.verification is not None
    assert outcome.receipt.request_digest == stable_digest_payload(
        prepared.request, workspace=tmp_path
    )
    assert outcome.receipt.host_executable_digest == "sha256:" + "a" * 64
    assert outcome.receipt.host_interpreter_digest == "sha256:" + "b" * 64
    assert "REQUEST_DIGEST_BOUND" in outcome.verification.checks
    assert "HOST_EXECUTABLE_PROVENANCE_BOUND" in outcome.verification.checks
    assert "HOST_INTERPRETER_PROVENANCE_BOUND" in outcome.verification.checks
    assert public_data(outcome.receipt)["request_digest"] == outcome.receipt.request_digest


def test_capability_change_after_host_completion_fails_closed(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)

    class MutatingHost(FakeHost):
        def request_invocation(self, request, *, budget, cancel_event=None):
            skill_path = Path(request.skill_path)
            skill_path.write_text(
                skill_path.read_text(encoding="utf-8") + "changed during host call\n",
                encoding="utf-8",
            )
            return super().request_invocation(
                request,
                budget=budget,
                cancel_event=cancel_event,
            )

    host = MutatingHost()
    engine = InvocationEngine(host)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-TOCTOU",
        run_id="RUN-P4-TOCTOU",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )

    outcome = engine.execute_prepared(prepared)

    assert host.calls == 1
    assert outcome.status is InvocationResultStatus.FAILURE
    assert "CAPABILITY_CHANGED_DURING_INVOCATION" in outcome.blockers
    assert outcome.artifacts == ()


def test_stale_package_after_authorization_blocks_without_host_call(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    host = FakeHost()
    engine = InvocationEngine(host)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-STALE",
        run_id="RUN-P4-STALE",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    skill = Path(record.path) / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")

    outcome = engine.execute_prepared(prepared)

    assert host.calls == 0
    assert outcome.status is InvocationResultStatus.BLOCKED
    assert "CAPABILITY_STALE_BEFORE_EXECUTION" in outcome.blockers


def test_lifecycle_rejects_skipping_authorization() -> None:
    with pytest.raises(LifecycleError):
        transition((InvocationLifecycle.DISCOVERED,), InvocationLifecycle.EXECUTING)


def test_controlled_real_replay_is_blocked_without_a_second_host_call(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    host = FakeHost()
    engine = InvocationEngine(host)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-REPLAY",
        run_id="RUN-P4-REPLAY",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )

    first = engine.execute_prepared(prepared)
    second = engine.execute_prepared(prepared)

    assert first.status is InvocationResultStatus.SUCCESS
    assert second.status is InvocationResultStatus.BLOCKED
    assert "REPLAY_DETECTED" in second.blockers
    assert host.calls == 1


def test_prepared_mode_upgrade_is_blocked_before_host_call(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    host = FakeHost()
    engine = InvocationEngine(host)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-MODE-TAMPER",
        run_id="RUN-P4-MODE-TAMPER",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.DRY_RUN,
        budget=Phase4Budget(),
    )
    object.__setattr__(prepared, "mode", ExecutionMode.CONTROLLED_REAL)

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.BLOCKED
    assert "PREPARED_MODE_MISMATCH" in outcome.blockers
    assert host.calls == 0


def test_request_task_tampering_is_blocked_before_host_call(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    host = FakeHost()
    engine = InvocationEngine(host)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-TASK-TAMPER",
        run_id="RUN-P4-TASK-TAMPER",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert prepared.request is not None
    object.__setattr__(prepared.request, "task", "Run an unauthorized command.")

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.BLOCKED
    assert "REQUEST_TASK_DIGEST_MISMATCH" in outcome.blockers
    assert host.calls == 0


def test_authorized_scope_tampering_is_blocked_before_host_call(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    host = FakeHost()
    engine = InvocationEngine(host)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-SCOPE-TAMPER",
        run_id="RUN-P4-SCOPE-TAMPER",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert prepared.preflight.authorization is not None
    object.__setattr__(prepared.preflight.authorization, "scope", "GLOBAL")

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.BLOCKED
    assert "AUTHORIZED_SCOPE_MISMATCH" in outcome.blockers
    assert host.calls == 0


def test_persistent_replay_is_blocked_after_engine_restart(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    ledger = tmp_path / ".harness" / "phase4" / "invocation-ledger.json"
    first_host = FakeHost()
    first = InvocationEngine(first_host, replay_ledger=ledger)
    prepared = first.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-PERSISTENT-REPLAY",
        run_id="RUN-P4-PERSISTENT-REPLAY",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert first.execute_prepared(prepared).status is InvocationResultStatus.SUCCESS

    second_host = FakeHost()
    second = InvocationEngine(second_host, replay_ledger=ledger)
    replay = second.execute_prepared(prepared)

    assert replay.status is InvocationResultStatus.BLOCKED
    assert "REPLAY_DETECTED" in replay.blockers
    assert second_host.calls == 0


def test_receipt_binding_is_verified_as_part_of_success(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    engine = InvocationEngine(FakeHost())
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-RECEIPT-BINDING",
        run_id="RUN-P4-RECEIPT-BINDING",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )

    outcome = engine.execute_prepared(prepared)

    assert outcome.verification is not None
    assert "RECEIPT_REFERENCE_CORRELATED" in outcome.verification.checks
    assert outcome.receipt.receipt_digest.startswith("sha256:")


def test_dataclass_replace_cannot_upgrade_prepared_mode(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    prepared = InvocationEngine(FakeHost()).prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-REPLACE-TAMPER",
        run_id="RUN-P4-REPLACE-TAMPER",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.DRY_RUN,
        budget=Phase4Budget(),
    )

    with pytest.raises(ValueError, match="prepared mode"):
        replace(prepared, mode=ExecutionMode.CONTROLLED_REAL)


def test_cancelled_before_host_start_never_calls_host(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    host = FakeHost()
    engine = InvocationEngine(host)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-CANCEL",
        run_id="RUN-P4-CANCEL",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    cancelled = Event()
    cancelled.set()

    outcome = engine.execute_prepared(prepared, cancel_event=cancelled)

    assert outcome.status is InvocationResultStatus.CANCELLED
    assert outcome.host_invoked is False
    assert host.calls == 0


def test_success_without_host_execution_observation_fails_closed(tmp_path: Path) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    host = FakeHost(
        result=HostInvocationResult(
            status=InvocationResultStatus.SUCCESS,
            thread_id="thread-1",
            session_id="session-1",
            turn_id="turn-1",
            host_version="fake",
            events=(),
            final_message="PHASE4_SAFE_PILOT_ARTIFACT",
            load_observation=HostLoadObservation.UNOBSERVABLE,
            invocation_observed=True,
            execution_observed=False,
            denied_approvals=0,
            cancellation_status="NOT_REQUESTED",
            error_code=None,
            started_at=1_700_000_000,
            completed_at=1_700_000_001,
            host_executable_path="/bin/codex-test",
            host_executable_digest="sha256:" + "a" * 64,
            host_command=("/bin/codex-test",),
            host_interpreter_path="/bin/node-test",
            host_interpreter_digest="sha256:" + "b" * 64,
        )
    )
    engine = InvocationEngine(host)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-UNOBSERVED",
        run_id="RUN-P4-UNOBSERVED",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.FAILURE
    assert "HOST_EXECUTION_UNOBSERVED" in outcome.blockers
