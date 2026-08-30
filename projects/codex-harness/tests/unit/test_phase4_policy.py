from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from harness_kernel.phase3_host import CodexHostAdapter
from harness_kernel.phase3_resolution import ResolutionEngine
from harness_kernel.phase4_models import ExecutionMode, Phase4Budget, stable_digest_payload
from harness_kernel.phase4_policy import (
    ExecutionPolicyRegistry,
    PilotRule,
    build_preflight,
)


def _discovered_record(tmp_path: Path):
    package = tmp_path / ".agents" / "skills" / "safe-pilot"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: safe-pilot\nversion: 0.1.0\n---\n"
        "Return a bounded response. Do not use tools, scripts, shell, network, MCP, "
        "providers, or files.\n",
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
    return record, inventory, resolution


def _policy(record) -> ExecutionPolicyRegistry:
    return ExecutionPolicyRegistry(
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
                reason="script-free fixture used because preferred installed pilots are ineligible",
            ),
        )
    )


def test_preflight_requires_exact_allowlist_and_fingerprint(tmp_path: Path) -> None:
    record, inventory, resolution = _discovered_record(tmp_path)
    policy = _policy(record)

    allowed = build_preflight(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-1",
        run_id="RUN-P4-1",
        task="Produce one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.PREPARE_ONLY,
        budget=Phase4Budget(),
        now=1_700_000_000,
    )

    assert allowed.allowed is True
    assert allowed.authorization is not None
    assert allowed.context is not None
    assert allowed.context.package_fingerprint == record.content_hash
    assert allowed.authorization.host_interpreter_digest == "sha256:" + "b" * 64
    assert (
        allowed.authorization.filesystem_policy["host_interpreter_digest"] == "sha256:" + "b" * 64
    )
    assert allowed.authorization.filesystem_policy == {
        "workspace": str(tmp_path.resolve()),
        "mode": "READ_ONLY",
        "allowed_roots": (),
        "package_path": str(Path(record.path).resolve()),
        "package_write_allowed": False,
        "network": "DENY",
        "shell": "DENY",
        "mcp": "DENY",
        "providers": "DENY",
        "credentials": "DENY",
        "max_files": 256,
        "max_bytes": 16 * 1024 * 1024,
        "artifact_root": str(tmp_path / ".harness" / "phase4" / "artifacts"),
        "host_executable_digest": "sha256:" + "a" * 64,
        "host_interpreter_digest": "sha256:" + "b" * 64,
    }
    context = allowed.context
    expected_context_payload = {
        "task_id": context.task_id,
        "task_digest": context.task_digest,
        "capability_id": context.capability_id,
        "package_fingerprint": context.package_fingerprint,
        "skill_path": context.skill_path,
        "sources": context.sources,
        "selected_references": context.selected_references,
        "omitted_references": context.omitted_references,
        "estimated_bytes": context.estimated_bytes,
        "acceptance_criteria": context.acceptance_criteria,
    }
    assert context.digest == stable_digest_payload(expected_context_payload, workspace=tmp_path)

    blocked_policy = ExecutionPolicyRegistry(
        (
            PilotRule(
                capability_id=record.capability_id,
                version=record.version,
                package_fingerprint="sha256:" + "0" * 64,
            ),
        )
    )
    blocked = build_preflight(
        record,
        inventory,
        resolution,
        blocked_policy,
        task_id="TASK-P4-2",
        run_id="RUN-P4-2",
        task="Produce one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert blocked.allowed is False
    assert "CAPABILITY_FINGERPRINT_MISMATCH" in blocked.blockers


def test_preflight_rejects_declared_scripts_and_unsafe_workspace(tmp_path: Path) -> None:
    record, inventory, resolution = _discovered_record(tmp_path)
    script = Path(record.path) / "scripts"
    script.mkdir()
    (script / "run.sh").write_text("echo forbidden\n", encoding="utf-8")
    adapter = CodexHostAdapter(
        project_root=tmp_path,
        home_dir=tmp_path / "no-home",
        codex_home=tmp_path / "no-codex-home",
    )
    current = next(
        item
        for item in adapter.discover_capabilities().capabilities
        if item.capability_id == "safe-pilot"
    )
    current_inventory = adapter.discover_capabilities()
    current_resolution = ResolutionEngine().resolve(current_inventory, "safe-pilot")
    result = build_preflight(
        current,
        current_inventory,
        current_resolution,
        _policy(current),
        task_id="TASK-P4-3",
        run_id="RUN-P4-3",
        task="Produce one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert result.allowed is False
    assert "FORBIDDEN_SCRIPT" in result.blockers

    outside = tmp_path.parent / "outside-pilot"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "escape"
    link.symlink_to(outside, target_is_directory=True)
    unsafe = build_preflight(
        record,
        inventory,
        resolution,
        _policy(record),
        task_id="TASK-P4-4",
        run_id="RUN-P4-4",
        task="Produce one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=link,
        mode=ExecutionMode.PREPARE_ONLY,
        budget=Phase4Budget(),
    )
    assert unsafe.allowed is False
    assert "WORKSPACE_SYMLINK" in unsafe.blockers


def test_controlled_real_preflight_requires_interpreter_binding(tmp_path: Path) -> None:
    record, inventory, resolution = _discovered_record(tmp_path)
    rule = _policy(record).rules[0]
    policy = ExecutionPolicyRegistry((replace(rule, host_interpreter_digest=None),))

    result = build_preflight(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-INTERPRETER-BINDING",
        run_id="RUN-P4-INTERPRETER-BINDING",
        task="Produce one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )

    assert result.allowed is False
    assert "HOST_INTERPRETER_NOT_BOUND" in result.blockers


def test_policy_registry_round_trips_without_secrets(tmp_path: Path) -> None:
    payload = {
        "schema_version": "P4-POLICY-1",
        "rules": [
            {
                "capability_id": "safe-pilot",
                "version": "0.1.0",
                "package_fingerprint": "sha256:" + "1" * 64,
                "execution_approved": False,
                "allowed_modes": ["DRY_RUN", "PREPARE_ONLY"],
                "reason": "inspection only",
            }
        ],
    }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    policy = ExecutionPolicyRegistry.from_json(path)
    assert policy.rules[0].execution_approved is False
    assert "secret" not in json.dumps(policy.to_dict()).lower()


def test_policy_parser_rejects_non_boolean_permissions() -> None:
    payload = {
        "schema_version": "P4-POLICY-1",
        "rules": [
            {
                "capability_id": "safe-pilot",
                "version": "0.1.0",
                "package_fingerprint": "sha256:" + "1" * 64,
                "execution_approved": "true",
                "reason": "invalid test",
            }
        ],
    }
    with pytest.raises(ValueError, match="execution_approved"):
        ExecutionPolicyRegistry.from_mapping(payload)


def test_preflight_blocks_resolution_mismatch_and_unsupported_real_policies(
    tmp_path: Path,
) -> None:
    record, inventory, resolution = _discovered_record(tmp_path)
    mismatched = ResolutionEngine().resolve(inventory, "missing-capability")
    blocked = build_preflight(
        record,
        inventory,
        mismatched,
        _policy(record),
        task_id="TASK-P4-MISMATCH",
        run_id="RUN-P4-MISMATCH",
        task="Produce one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert "RESOLUTION_RECORD_MISMATCH" in blocked.blockers

    manifest = replace(record.manifest, tools=("shell",), providers=("provider-x",))
    decorated = replace(record, manifest=manifest)
    permissive = ExecutionPolicyRegistry(
        (
            PilotRule(
                capability_id=record.capability_id,
                version=record.version,
                package_fingerprint=record.content_hash,
                host_executable_digest="sha256:" + "a" * 64,
                host_interpreter_digest="sha256:" + "b" * 64,
                execution_approved=True,
                allowed_modes=(ExecutionMode.CONTROLLED_REAL,),
                allowed_tools=("shell",),
                allowed_providers=("provider-x",),
                allowed_side_effects=("write",),
                allow_network=True,
                allow_shell=True,
                allow_mcp=True,
                allow_credentials=True,
                reason="unsupported policy test",
            ),
        )
    )
    unsupported = build_preflight(
        decorated,
        inventory,
        resolution,
        permissive,
        task_id="TASK-P4-UNSUPPORTED",
        run_id="RUN-P4-UNSUPPORTED",
        task="Produce one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert unsupported.allowed is False
    assert "HOST_TOOL_POLICY_UNSUPPORTED" in unsupported.blockers
    assert "HOST_PROVIDER_POLICY_UNSUPPORTED" in unsupported.blockers
    assert "HOST_NETWORK_POLICY_UNSUPPORTED" in unsupported.blockers
