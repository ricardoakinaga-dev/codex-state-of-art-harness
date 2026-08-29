from __future__ import annotations

from dataclasses import dataclass

import pytest

from harness_kernel.phase4_execution import InvocationEngine
from harness_kernel.phase4_models import (
    HostInvocationResult,
    HostLoadObservation,
    InvocationResultStatus,
)


@dataclass
class NeverCalledHost:
    calls: int = 0

    def prepare_invocation(self, request):
        return {"supported": True}

    def validate_invocation(self, request):
        return ()

    def request_invocation(self, request, *, budget, cancel_event=None):
        self.calls += 1
        return HostInvocationResult(
            status=InvocationResultStatus.SUCCESS,
            thread_id="thread",
            session_id="session",
            turn_id="turn",
            host_version="fake",
            events=(),
            final_message="unexpected",
            load_observation=HostLoadObservation.UNOBSERVABLE,
            invocation_observed=True,
            execution_observed=True,
            denied_approvals=0,
            cancellation_status="NOT_REQUESTED",
            error_code=None,
            started_at=1,
            completed_at=2,
            host_executable_path="/bin/codex-test",
            host_executable_digest="sha256:" + "a" * 64,
            host_command=("/bin/codex-test",),
            host_interpreter_path="/bin/node-test",
            host_interpreter_digest="sha256:" + "b" * 64,
        )


def test_missing_authorization_is_a_hard_boundary() -> None:
    host = NeverCalledHost()
    engine = InvocationEngine(host)

    with pytest.raises(TypeError):
        engine.execute_prepared(None)  # type: ignore[arg-type]
    assert host.calls == 0
