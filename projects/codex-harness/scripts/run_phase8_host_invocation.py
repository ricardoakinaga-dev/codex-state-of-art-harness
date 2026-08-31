"""Run one explicitly bounded Phase 4 invocation with host-only transport auth."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from harness_kernel.phase3_host import CodexHostAdapter
from harness_kernel.phase3_resolution import ResolutionEngine
from harness_kernel.phase4_evidence import EvidenceWriter, public_outcome, redact_paths
from harness_kernel.phase4_execution import InvocationEngine
from harness_kernel.phase4_host import CodexAppServerAdapter
from harness_kernel.phase4_models import ExecutionMode, Phase4Budget
from harness_kernel.phase4_policy import ExecutionPolicyRegistry


def run_invocation(
    *,
    project_root: Path,
    workspace: Path,
    policy_path: Path,
    capability: str,
    task: str,
    acceptance: tuple[str, ...],
    fingerprint: str,
    evidence_dir: Path,
    timeout: int,
) -> dict[str, object]:
    policy = ExecutionPolicyRegistry.from_json(policy_path)
    adapter = CodexHostAdapter(
        project_root=project_root,
        workspace_root=workspace,
        home_dir=Path.home(),
    )
    inventory = adapter.discover_capabilities()
    resolution = ResolutionEngine().resolve(inventory, capability)
    if not resolution.selected:
        raise ValueError(f"capability was not resolved: {capability}")
    record = resolution.selected[0]
    engine = InvocationEngine(CodexAppServerAdapter(host_authentication=True))
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P8-" + uuid.uuid4().hex[:12],
        run_id="RUN-P8-" + uuid.uuid4().hex[:12],
        task=task,
        acceptance_criteria=acceptance,
        workspace=workspace,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(timeout_seconds=timeout),
        expected_fingerprint=fingerprint,
        require_fingerprint_confirmation=True,
    )
    outcome = engine.execute_prepared(prepared)
    payload = public_outcome(outcome, workspace=workspace)
    payload["capability"] = record.capability_id
    payload["package_fingerprint"] = record.content_hash
    payload["host_authentication_mode"] = "HOST_ONLY_CONTROL_PLANE"
    EvidenceWriter(str(evidence_dir)).write_json(
        f"invocation-receipts/{outcome.receipt.invocation_id}.json", payload
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--capability", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--acceptance", action="append", required=True)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=90)
    arguments = parser.parse_args()
    project_root = arguments.project_root.resolve(strict=True)
    workspace = arguments.workspace.resolve(strict=True)
    policy_path = arguments.policy.resolve(strict=True)
    evidence_dir = arguments.evidence_dir
    evidence_dir = evidence_dir if evidence_dir.is_absolute() else project_root / evidence_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)
    payload = run_invocation(
        project_root=project_root,
        workspace=workspace,
        policy_path=policy_path,
        capability=arguments.capability,
        task=arguments.task,
        acceptance=tuple(arguments.acceptance),
        fingerprint=arguments.fingerprint,
        evidence_dir=evidence_dir,
        timeout=arguments.timeout,
    )
    print(json.dumps(redact_paths(payload), ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("status") == "SUCCESS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
