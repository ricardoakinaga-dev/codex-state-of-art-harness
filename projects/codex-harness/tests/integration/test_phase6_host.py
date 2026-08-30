from __future__ import annotations

import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from harness_kernel.cli import _manifest_files
from harness_kernel.phase3_discovery import CapabilityDiscovery
from harness_kernel.phase3_models import CapabilityKind, CapabilityLifecycle, DisclosureLevel
from harness_kernel.phase4_models import ExecutionMode, Phase4Budget
from harness_kernel.phase6_host import (
    Phase6AppServerAdapter,
    discover_vnext_package,
    prepare_vnext_preflight,
)

PROJECT_ROOT = Path(__file__).parents[2]


def test_project_local_vnext_is_discovered_native_and_loaded_metadata_only() -> None:
    snapshot = discover_vnext_package(PROJECT_ROOT)

    assert snapshot.record is not None
    assert snapshot.record.capability_id == "verification-loop-vnext"
    assert snapshot.record.kind is CapabilityKind.NATIVE
    assert snapshot.record.status is CapabilityLifecycle.INSPECTED
    assert snapshot.record.load_eligibility == "ELIGIBLE_DECLARATIVE_METADATA_ONLY"
    assert snapshot.load_level is DisclosureLevel.INSTRUCTION_KERNEL
    assert snapshot.instruction_loaded is True
    assert snapshot.host_load_observation == "UNAVAILABLE"
    assert snapshot.package_digest.startswith("sha256:")
    assert snapshot.manifest_digest.startswith("sha256:")
    assert snapshot.digest.startswith("sha256:")


def test_preflight_without_exact_project_policy_is_blocked_before_host_invocation() -> None:
    preflight = prepare_vnext_preflight(
        PROJECT_ROOT,
        task_id="TASK-P6-PREFLIGHT",
        run_id="RUN-P6-PREFLIGHT",
        task="Verify one declared local artifact.",
        acceptance_criteria=("artifact identity is bound",),
        policy_path=PROJECT_ROOT / "config" / "missing-phase6-policy.json",
    )

    assert preflight.allowed is False
    assert preflight.prepared is not None
    assert preflight.prepared.preflight.allowed is False
    assert "BLOCKED_EXECUTION_POLICY" in preflight.blockers
    assert preflight.host_invoked is False
    assert preflight.digest.startswith("sha256:")


def test_native_only_manifest_does_not_break_phase1_registry_discovery() -> None:
    paths = _manifest_files(PROJECT_ROOT)

    assert all(path.parent.name != "verification-loop-vnext" for path in paths)


def test_vnext_reaches_controlled_real_preflight_with_metadata_only_scripts() -> None:
    preflight = prepare_vnext_preflight(
        PROJECT_ROOT,
        task_id="TASK-P6-PILOT-PREFLIGHT",
        run_id="RUN-P6-PILOT-PREFLIGHT",
        task="Verify one declared local artifact.",
        acceptance_criteria=("artifact identity is bound",),
        policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
        mode=ExecutionMode.CONTROLLED_REAL,
    )

    assert preflight.allowed is True
    assert preflight.prepared is not None
    assert preflight.prepared.request is not None
    assert "SCRIPTS_METADATA_ONLY" not in preflight.blockers


def test_backend_builder_reaches_canonical_controlled_real_preflight() -> None:
    snapshot = discover_vnext_package(
        PROJECT_ROOT,
        capability_id="backend-engineering-vnext",
    )

    with tempfile.TemporaryDirectory(prefix="phase7-preflight-", dir=PROJECT_ROOT) as raw:
        workspace = Path(raw) / "pilot"
        for root in ("app", "migrations", "tests"):
            (workspace / root).mkdir(parents=True)

        preflight = prepare_vnext_preflight(
            PROJECT_ROOT,
            snapshot=snapshot,
            task_id="TASK-P7-CANONICAL-PREFLIGHT",
            run_id="RUN-P7-CANONICAL-PREFLIGHT",
            task="Build one bounded backend hardening change.",
            acceptance_criteria=("only the declared pilot roots change",),
            workspace=workspace,
            policy_path=PROJECT_ROOT / "config" / "phase7-execution-policy.json",
            mode=ExecutionMode.CONTROLLED_REAL,
            budget=Phase4Budget(timeout_seconds=30, max_tool_calls=0, max_host_events=128),
        )

        assert snapshot.record is not None
        assert snapshot.capability_id == "backend-engineering-vnext"
        assert snapshot.record.capability_id == "backend-engineering-vnext"
        assert preflight.allowed is True
        assert preflight.prepared is not None
        assert preflight.prepared.request is not None
        request = preflight.prepared.request
        assert request.authorization.filesystem_policy["mode"] == "WORKSPACE_WRITE"
        assert request.authorization.filesystem_policy["allowed_roots"] == tuple(
            str((workspace / root).resolve()) for root in ("app", "migrations", "tests")
        )
        assert preflight.host_invoked is False


def test_phase6_host_accepts_explicit_project_local_skill_fallback() -> None:
    preflight = prepare_vnext_preflight(
        PROJECT_ROOT,
        task_id="TASK-P6-LOCAL-SKILL",
        run_id="RUN-P6-LOCAL-SKILL",
        task="Verify one declared local artifact.",
        acceptance_criteria=("artifact identity is bound",),
        policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
        mode=ExecutionMode.CONTROLLED_REAL,
    )

    assert preflight.prepared is not None
    request = preflight.prepared.request
    assert request is not None
    assert Phase6AppServerAdapter._skill_is_discovered({}, request) is True


def test_phase6_host_fallback_rejects_a_symlink_skill_path(tmp_path) -> None:
    preflight = prepare_vnext_preflight(
        PROJECT_ROOT,
        task_id="TASK-P6-SYMLINK-SKILL",
        run_id="RUN-P6-SYMLINK-SKILL",
        task="Verify one declared local artifact.",
        acceptance_criteria=("artifact identity is bound",),
        policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
        mode=ExecutionMode.CONTROLLED_REAL,
    )
    assert preflight.prepared is not None
    request = preflight.prepared.request
    assert request is not None
    link = tmp_path / "skill-link"
    os.symlink(request.skill_path, link)
    object.__setattr__(request, "skill_path", str(link))

    assert Phase6AppServerAdapter._skill_is_discovered({}, request) is False


def test_phase6_host_fallback_rejects_an_arbitrary_regular_file(tmp_path) -> None:
    preflight = prepare_vnext_preflight(
        PROJECT_ROOT,
        task_id="TASK-P6-ARBITRARY-SKILL",
        run_id="RUN-P6-ARBITRARY-SKILL",
        task="Verify one declared local artifact.",
        acceptance_criteria=("artifact identity is bound",),
        policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
        mode=ExecutionMode.CONTROLLED_REAL,
    )
    assert preflight.prepared is not None
    request = preflight.prepared.request
    assert request is not None
    arbitrary = tmp_path / "SKILL.md"
    arbitrary.write_text("not a capability package", encoding="utf-8")
    object.__setattr__(request, "skill_path", str(arbitrary))

    assert Phase6AppServerAdapter._skill_is_discovered({}, request) is False


def test_phase6_host_fallback_rejects_a_minimal_native_manifest(tmp_path) -> None:
    preflight = prepare_vnext_preflight(
        PROJECT_ROOT,
        task_id="TASK-P6-MINIMAL-MANIFEST",
        run_id="RUN-P6-MINIMAL-MANIFEST",
        task="Verify one declared local artifact.",
        acceptance_criteria=("artifact identity is bound",),
        policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
        mode=ExecutionMode.CONTROLLED_REAL,
    )
    assert preflight.prepared is not None
    request = preflight.prepared.request
    assert request is not None
    fake_project = tmp_path / "fake-project"
    fake_workspace = fake_project / "workspace"
    fake_package = fake_project / ".harness" / "capabilities" / request.skill_name
    fake_workspace.mkdir(parents=True)
    fake_package.mkdir(parents=True)
    (fake_package / "SKILL.md").write_text("arbitrary", encoding="utf-8")
    (fake_package / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "CM-1",
                "capability_id": request.skill_name,
                "display_name": "Minimal",
                "version": request.authorization.capability_version,
            }
        ),
        encoding="utf-8",
    )
    object.__setattr__(request, "workspace", str(fake_workspace))
    object.__setattr__(request, "skill_path", str(fake_package / "SKILL.md"))

    assert Phase6AppServerAdapter._skill_is_discovered({}, request) is False


def test_phase6_host_fallback_rejects_any_native_discovery_error(monkeypatch) -> None:
    preflight = prepare_vnext_preflight(
        PROJECT_ROOT,
        task_id="TASK-P6-DISCOVERY-ERROR",
        run_id="RUN-P6-DISCOVERY-ERROR",
        task="Verify one declared local artifact.",
        acceptance_criteria=("artifact identity is bound",),
        policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
        mode=ExecutionMode.CONTROLLED_REAL,
    )
    assert preflight.prepared is not None
    request = preflight.prepared.request
    assert request is not None
    original_scan = CapabilityDiscovery.scan

    def scan_with_error(self, roots, *, expected_fingerprint=None):
        inventory = original_scan(self, roots, expected_fingerprint=expected_fingerprint)
        return replace(inventory, errors=(*inventory.errors, "unrelated scan error"))

    monkeypatch.setattr(CapabilityDiscovery, "scan", scan_with_error)

    assert Phase6AppServerAdapter._skill_is_discovered({}, request) is False


def test_phase6_preflight_rejects_policy_outside_project_root(tmp_path) -> None:
    outside_policy = tmp_path / "phase6-policy.json"
    outside_policy.write_text("{}", encoding="utf-8")
    preflight = prepare_vnext_preflight(
        PROJECT_ROOT,
        task_id="TASK-P6-OUTSIDE-POLICY",
        run_id="RUN-P6-OUTSIDE-POLICY",
        task="Verify one declared local artifact.",
        acceptance_criteria=("artifact identity is bound",),
        policy_path=outside_policy,
        mode=ExecutionMode.CONTROLLED_REAL,
    )

    assert preflight.allowed is False
    assert "EXECUTION_POLICY_UNAVAILABLE" in preflight.blockers
