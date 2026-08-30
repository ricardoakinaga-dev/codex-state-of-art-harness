from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from harness_kernel.phase4_host import CodexAppServerAdapter
from harness_kernel.phase4_models import (
    CapabilityExecutionAuthorization,
    CapabilityInvocationRequest,
    ContextManifest,
    ExecutionMode,
    digest_payload,
)


def test_official_app_server_ephemeral_handshake_is_available(monkeypatch) -> None:
    project = Path(__file__).parents[2]
    codex = shutil.which("codex")
    node = shutil.which("node")
    if not codex or not node:
        pytest.skip("Codex and Node are not available for the real-host smoke test")
    monkeypatch.setenv("CODEX_EXECUTABLE", os.path.realpath(codex))
    monkeypatch.setenv("NODE_EXECUTABLE", os.path.realpath(node))
    skill_path = Path("/home/ricardo/.agents/skills/coding-standards/SKILL.md")
    authorization = CapabilityExecutionAuthorization(
        authorization_id="AUTH-P4-SMOKE",
        task_id="TASK-P4-SMOKE",
        run_id="RUN-P4-SMOKE",
        capability_id="coding-standards",
        capability_version="0.1.0",
        package_fingerprint="sha256:" + "0" * 64,
        scope="GLOBAL",
        requested_loading_level="L2_INSTRUCTION_KERNEL",
        requested_execution_mode=ExecutionMode.PREPARE_ONLY,
        allowed_tools=(),
        allowed_side_effects=(),
        filesystem_policy={"workspace": str(project), "mode": "READ_ONLY"},
        network_policy="DENY",
        shell_policy="DENY",
        provider_policy="DENY",
        mcp_policy="DENY",
        credential_policy="DENY",
        timeout_seconds=20,
        iteration_budget={"host_calls": 1},
        context_budget={"max_bytes": 8_000},
        artifact_policy={"types": []},
        evidence_policy={"max_events": 40},
        issued_by="test",
        issued_at=1_700_000_000,
        expires_at=1_700_000_020,
        reason="handshake smoke",
        constraints=(),
    )
    request = CapabilityInvocationRequest(
        invocation_id="INV-P4-SMOKE",
        authorization=authorization,
        context=ContextManifest(
            task_id=authorization.task_id,
            task_digest=digest_payload("Reply with exactly OK. Do not call tools or modify files."),
            capability_id=authorization.capability_id,
            package_fingerprint=authorization.package_fingerprint,
            skill_path=str(skill_path),
            sources=("HOST_MANAGED_SKILL",),
            selected_references=(),
            omitted_references=(),
            estimated_bytes=100,
            digest="sha256:" + "1" * 64,
            acceptance_criteria=("reply is bounded",),
        ),
        skill_name="coding-standards",
        skill_path=str(skill_path),
        task="Reply with exactly OK. Do not call tools or modify files.",
        acceptance_criteria=("reply is bounded",),
        workspace=str(project),
        expected_artifacts=(),
        idempotency_key="idem-p4-smoke",
    )

    adapter = CodexAppServerAdapter()
    preparation = adapter.prepare_invocation(request)

    assert preparation.supported is True
    assert adapter.validate_invocation(request) == ()
