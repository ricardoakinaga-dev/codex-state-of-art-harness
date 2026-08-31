"""Focused tests for the Phase 7.3 exact review manifest."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from generate_phase73_manifest import build_manifest, write_outputs  # noqa: E402


def test_manifest_binds_current_phase73_packet_without_self_recursion() -> None:
    manifest = build_manifest()

    assert manifest["schema_version"] == "P7.3-REVIEW-MANIFEST-1"
    assert manifest["feature_freeze"] == "P7_3_FEATURE_FREEZE"
    assert manifest["reviewed_head"]
    assert manifest["manifest_digest"].startswith("sha256:")
    paths = {entry["path"] for entry in manifest["entries"]}
    assert "evidence/phase-7.3/final-report.md" in paths
    assert "evidence/phase-7.3/material-medium-proof.json" in paths
    assert "evidence/phase-7.3/review-manifest.json" not in paths
    assert "evidence/phase-7.3/real-cycle-final-001/builder/builder-receipt.json" not in paths
    assert "evidence/phase-7.3/real-cycle-final-004/builder/builder-receipt.json" not in paths
    assert (
        "evidence/phase-7.3/phase72-final/traceability/branch-test-traceability.json" not in paths
    )
    assert ".agent/state.json" in paths
    assert ".agent/execution-log.jsonl" in paths
    assert manifest["source_fingerprint"]["file_count"] > 0
    assert manifest["tests_fingerprint"]["file_count"] > 0
    assert manifest["authoritative_phase72_inventory"] == (
        "evidence/phase-7.2/high-risk-branch-inventory.json"
    )
    assert manifest["material_medium_proof"] == "evidence/phase-7.3/material-medium-proof.json"
    assert manifest["branch_traceability"] == (
        "evidence/phase-7.3/phase73-current/traceability/branch-test-traceability.json"
    )
    assert manifest["real_cycle"] == "evidence/phase-7.3/real-cycle-report-005.json"
    assert manifest["materiality_review"] == "evidence/phase-7.3/materiality-review.json"


def test_manifest_attestation_exposes_review_and_promotion_fields(tmp_path: Path) -> None:
    manifest = build_manifest()
    original_evidence_root = __import__("generate_phase73_manifest").EVIDENCE_ROOT
    try:
        __import__("generate_phase73_manifest").EVIDENCE_ROOT = tmp_path
        write_outputs(manifest)
    finally:
        __import__("generate_phase73_manifest").EVIDENCE_ROOT = original_evidence_root

    import json

    attestation = json.loads((tmp_path / "review-attestation.json").read_text(encoding="utf-8"))
    assert attestation["review_mode"] == "FRESH_READ_ONLY_EXACT_PACKET"
    assert attestation["critical_open"] == 0
    assert attestation["actionable_medium"] == 0
    assert attestation["scanner_waiver_accepted"] is True
