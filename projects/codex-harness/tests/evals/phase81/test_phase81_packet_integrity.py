"""RED-first tests for the Phase 8.1 packet integrity verifier."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).parents[3]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-8.1"


def _load_script(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"phase81_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_phase8_evals = _load_script("run_phase8_evals")
packet_validator = _load_script("validate_phase81_packet")
ALLOWED_COMPOSITION_STATUSES = packet_validator.ALLOWED_COMPOSITION_STATUSES
validate_composition_status = packet_validator.validate_composition_status
validate_identity = packet_validator.validate_identity
validate_review_manifest = packet_validator.validate_review_manifest


def test_structural_evaluator_reports_zero_observed_critical_false_passes() -> None:
    report = run_phase8_evals.evaluate(PROJECT_ROOT)

    assert report["critical_false_pass_count"] == 0
    assert report["critical_false_pass"] == []
    assert report["false_pass_guard_ids"]


def test_composition_status_vocabulary_excludes_report_status() -> None:
    assert "PASS_WITH_LIMITATIONS" not in ALLOWED_COMPOSITION_STATUSES
    assert validate_composition_status("PARTIAL") == []
    assert validate_composition_status("PASS_WITH_LIMITATIONS")


def test_identity_validator_rejects_a_stale_repository_head() -> None:
    errors = validate_identity(
        {
            "readiness": {"repository_head": "old-head"},
            "manifest": {"repository_head": "old-head"},
            "attestation": {"repository_head": "old-head"},
            "verifier": {"repository_head": "old-head"},
        },
        current_head="current-head",
    )

    assert any("repository_head" in error for error in errors)


def test_manifest_validator_rejects_a_tampered_entry_without_mutating_input() -> None:
    manifest = json.loads((EVIDENCE_ROOT / "review-manifest.json").read_text(encoding="utf-8"))
    original = copy.deepcopy(manifest)
    entry = next(item for item in manifest["entries"] if item["path"] == "README.md")
    entry["sha256"] = "sha256:" + hashlib.sha256(b"tampered").hexdigest()

    errors = validate_review_manifest(manifest, EVIDENCE_ROOT)

    assert errors
    assert manifest != original
    assert original["entries"] != manifest["entries"]


def test_validator_source_has_no_write_surface() -> None:
    source = Path(__file__).parents[3] / "scripts" / "validate_phase81_packet.py"
    text = source.read_text(encoding="utf-8")

    assert ".write_text(" not in text
    assert "mkdir(" not in text
    assert "unlink(" not in text


@pytest.mark.parametrize("status", sorted(ALLOWED_COMPOSITION_STATUSES))
def test_allowed_composition_statuses_are_explicit(status: str) -> None:
    assert validate_composition_status(status) == []
