#!/usr/bin/env python3
"""Generate the evidence packet for the real Phase 6 vNext pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from harness_kernel.phase4_models import public_data as phase4_public_data
from harness_kernel.phase5_models import ArtifactPacket
from harness_kernel.phase5_pilot import load_task
from harness_kernel.phase6_composition import (
    build_verification_input,
    build_verification_plan,
    invoke_vnext_host_probe,
    prepare_vnext_host_preflight,
    run_verification_plan,
    verification_public_data,
)
from harness_kernel.phase6_host import discover_vnext_package
from harness_kernel.phase6_models import VerificationStatus, public_data


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(public_data(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_phase4_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(phase4_public_data(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_builder_handoff(pilot_dir: Path, packet: ArtifactPacket) -> Path:
    """Bind the producer invocation to the historical Phase 5 host receipt."""

    source_path = (pilot_dir / "builder-invocation-receipt.json").resolve()
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes.decode("utf-8"))
    if not isinstance(source, dict):
        raise RuntimeError("builder invocation receipt is not an object")
    attempts = source.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise RuntimeError("builder invocation receipt has no host attempt")
    attempt = attempts[-1]
    if not isinstance(attempt, dict):
        raise RuntimeError("builder invocation attempt is invalid")
    required = {
        "task_id": packet.task_id,
        "run_id": source.get("run_id"),
        "status": "PASS",
        "artifact_id": packet.artifact_id,
        "artifact_version": packet.version,
        "artifact_path": packet.path,
        "artifact_digest": packet.digest,
        "artifact_size_bytes": packet.size_bytes,
        "producer_capability": packet.producer_capability,
    }
    if any(source.get(key) != value for key, value in required.items()):
        raise RuntimeError("historical builder receipt is not bound to the artifact packet")
    host_invocation_id = attempt.get("invocation_id")
    if not isinstance(host_invocation_id, str) or not host_invocation_id:
        raise RuntimeError("historical builder host invocation is missing")
    handoff = {
        "schema_version": "P6-BUILDER-HANDOFF-1",
        "task_id": packet.task_id,
        "run_id": source["run_id"],
        "status": "PASS",
        "artifact_id": packet.artifact_id,
        "artifact_version": packet.version,
        "artifact_path": packet.path,
        "artifact_digest": packet.digest,
        "artifact_size_bytes": packet.size_bytes,
        "acceptance_digest": packet.acceptance_digest,
        "producer_capability": packet.producer_capability,
        "producer_invocation_id": packet.invocation_id,
        "host_invocation_id": host_invocation_id,
        "host_load_observation": attempt.get("load_observation"),
        "authorization_id": attempt.get("authorization_id"),
        "context_digest": attempt.get("context_digest"),
        "package_fingerprint": source.get("package_fingerprint"),
        "manifest_fingerprint": source.get("manifest_fingerprint"),
        "source_receipt_path": str(source_path),
        "source_receipt_digest": "sha256:" + hashlib.sha256(source_bytes).hexdigest(),
    }
    handoff_path = pilot_dir / "builder-handoff-receipt.json"
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return handoff_path


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--invocation-label", default="EVIDENCE-01")
    return parser


def main() -> int:
    args = _arg_parser().parse_args()
    project_root = args.project_root.resolve()
    pilot_dir = args.pilot_dir.resolve()
    task = load_task(pilot_dir / "task.json", project_root=project_root)
    packet_payload = json.loads(
        (pilot_dir / "artifact-v1" / "packet.json").read_text(encoding="utf-8")
    )
    packet = ArtifactPacket(**packet_payload)
    desktop = pilot_dir / "browser" / "desktop-1440x900.jpg"
    mobile = pilot_dir / "browser" / "mobile-390x844.jpg"
    browser_manifest = pilot_dir / "browser" / "browser-capture-manifest.json"
    builder_receipt = _write_builder_handoff(pilot_dir, packet)
    snapshot = discover_vnext_package(project_root)
    if snapshot.package_digest is None or snapshot.manifest_digest is None:
        raise RuntimeError("vNext discovery did not produce exact package identity")

    plan = build_verification_plan(
        task,
        packet,
        desktop_render=desktop,
        mobile_render=mobile,
        builder_receipt=builder_receipt,
        browser_manifest=browser_manifest,
        snapshot=snapshot,
    )
    initial_input = build_verification_input(
        task,
        packet,
        plan,
        desktop_render=desktop,
        mobile_render=mobile,
        builder_receipt=builder_receipt,
        browser_manifest=browser_manifest,
        snapshot=snapshot,
        observed_at=int(time.time()),
    )
    verification_run = run_verification_plan(plan, initial_input)
    preflight = prepare_vnext_host_preflight(
        task,
        packet,
        snapshot=snapshot,
        policy_path=args.policy,
        plan=plan,
        verification_input=verification_run.verification_input,
        invocation_label=args.invocation_label,
    )
    probe, outcome = invoke_vnext_host_probe(
        task,
        packet,
        snapshot=snapshot,
        policy_path=args.policy,
        plan=plan,
        verification_input=verification_run.verification_input,
        expected_output=verification_run.output,
        preflight=preflight,
        invocation_label=args.invocation_label,
    )
    response = outcome.host_result.final_message if outcome.host_result else None
    if response:
        (pilot_dir / "host-response.txt").write_text(response, encoding="utf-8")

    discovery_summary: dict[str, Any] = {
        "schema_version": "P6-DISCOVERY-1",
        "capability_id": snapshot.capability_id,
        "kind": snapshot.record.kind.value if snapshot.record else None,
        "status": snapshot.record.status.value if snapshot.record else None,
        "scope": snapshot.record.scope.value if snapshot.record else None,
        "canonical_path": snapshot.record.path if snapshot.record else None,
        "version": snapshot.record.version if snapshot.record else None,
        "load_eligibility": snapshot.record.load_eligibility if snapshot.record else None,
        "load_level": snapshot.load_level.value,
        "instruction_loaded": snapshot.instruction_loaded,
        "host_load_observation": snapshot.host_load_observation,
        "package_digest": snapshot.package_digest,
        "manifest_digest": snapshot.manifest_digest,
        "snapshot_digest": snapshot.digest,
        "blockers": snapshot.blockers,
        "original_installed_capability_preserved": True,
        "global_state_mutation": False,
    }
    preflight_summary = {
        "schema_version": "P6-PREFLIGHT-REPORT-1",
        "allowed": preflight.allowed,
        "mode": preflight.mode.value,
        "blockers": preflight.blockers,
        "warnings": preflight.warnings,
        "preflight_digest": preflight.digest,
        "snapshot_digest": preflight.snapshot.digest,
        "host_invoked": preflight.host_invoked,
        "phase4_preflight_digest": (
            preflight.prepared.preflight.digest if preflight.prepared is not None else None
        ),
        "prepared_invocation_id": (
            preflight.prepared.request.invocation_id
            if preflight.prepared is not None and preflight.prepared.request is not None
            else None
        ),
        "host_run_id": (
            preflight.prepared.request.authorization.run_id
            if preflight.prepared is not None and preflight.prepared.request is not None
            else None
        ),
    }
    composition_receipt = {
        "schema_version": "P6-COMPOSITION-RECEIPT-1",
        "task_id": task.task_id,
        "run_id": task.run_id,
        "pipeline": ["ROUTER", "DESIGN_DIRECTOR", "VERIFICATION_LOOP_VNEXT", "ASSURANCE"],
        "status": "PASS_WITH_LIMITATIONS"
        if packet.acceptance_digest == task.criteria.digest
        and verification_run.output.status is VerificationStatus.PASS
        and probe.status is VerificationStatus.PASS
        else "FAIL",
        "support_level": "P6_LEVEL_B"
        if verification_run.output.status is VerificationStatus.PASS
        and probe.status is VerificationStatus.PASS
        else "P6_LEVEL_A",
        "criteria_frozen_before_builder": True,
        "deferred_qualitative_criteria": [
            {"criterion_id": item, "status": "NOT_RUN", "authority": "REVIEWER"}
            for item in plan.deferred_criteria
        ],
        "criteria_digest": task.criteria.digest,
        "builder_capability": packet.producer_capability,
        "builder_invocation_id": packet.invocation_id,
        "builder_host_invocation_id": json.loads(builder_receipt.read_text(encoding="utf-8"))[
            "host_invocation_id"
        ],
        "builder_handoff_receipt_digest": (
            "sha256:" + hashlib.sha256(builder_receipt.read_bytes()).hexdigest()
        ),
        "builder_artifact": public_data(packet),
        "verifier_capability": "verification-loop-vnext",
        "verifier_package_digest": snapshot.package_digest,
        "verifier_manifest_digest": snapshot.manifest_digest,
        "verification_plan_digest": plan.digest,
        "verification_report_digest": verification_run.output.report_digest,
        "host_probe": public_data(probe),
        "host_report_binding": {
            "status": "PASS" if probe.report_valid else "FAIL",
            "input_digest": verification_run.verification_input.digest,
            "report_digest": verification_run.output.report_digest,
            "criteria_digest": task.criteria.digest,
        },
        "host_receipt_digest": outcome.receipt.receipt_digest,
        "host_preflight_digest": preflight.digest,
        "host_phase4_preflight_digest": (
            preflight.prepared.preflight.digest if preflight.prepared is not None else None
        ),
        "host_invocation_id": probe.invocation_id,
        "independent_critic": {"status": "NOT_RUN", "required_for": "P6_LEVEL_C"},
        "repair": {"status": "NOT_RUN", "required_for": "P6_LEVEL_C"},
        "limitations": [
            "host_skill_load_event_unobservable",
            "visual_quality_authority_excluded_from_factual_verifier",
        ],
    }
    _write_json(pilot_dir / "vnext-discovery.json", discovery_summary)
    _write_json(pilot_dir / "vnext-execution-preflight.json", preflight_summary)
    _write_json(pilot_dir / "verification-plan.json", plan)
    _write_json(pilot_dir / "verification-input.json", verification_run.verification_input)
    _write_json(
        pilot_dir / "verification-report-v1.json", verification_public_data(verification_run)
    )
    _write_json(pilot_dir / "verification-telemetry.json", verification_run.telemetry)
    _write_json(pilot_dir / "verification-report.json", public_data(verification_run.output))
    _write_json(pilot_dir / "host-probe.json", probe)
    _write_phase4_json(pilot_dir / "host-invocation-receipt.json", outcome.receipt)
    _write_phase4_json(pilot_dir / "host-verification.json", outcome.verification)
    _write_phase4_json(pilot_dir / "host-assurance.json", outcome.assurance)
    _write_json(pilot_dir / "composition-receipt.json", composition_receipt)
    print(
        json.dumps(
            {
                "status": composition_receipt["status"],
                "support_level": composition_receipt["support_level"],
                "verification_status": verification_run.output.status.value,
                "verification_digest": verification_run.output.report_digest,
                "host_probe_status": probe.status.value,
                "host_invocation_id": probe.invocation_id,
                "host_receipt_digest": probe.receipt_digest,
                "package_digest": snapshot.package_digest,
                "manifest_digest": snapshot.manifest_digest,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
