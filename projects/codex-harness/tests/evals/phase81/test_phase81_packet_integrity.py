"""RED-first tests for the Phase 8.1 packet integrity verifier."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

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
validate_composition_chain = packet_validator.validate_composition_chain


def _valid_chain() -> tuple[dict[str, Any], ...]:
    run = "P81-COMPOSE-013"
    artifact = "sha256:artifact"
    browser_digest = "sha256:browser"
    verifier_digest = "sha256:verifier"
    workspace = "frontend-real-005/workspace-post/app"
    receipt: dict[str, Any] = {
        "status": "PROVEN_WITH_OBSERVABLE_ALTERNATIVE_CAUSALITY",
        "run_id": run,
        "artifact_digest": artifact,
        "source_digest": artifact,
        "build_digest": artifact,
        "composition_artifact_digest": artifact,
        "browser_evidence_digest": browser_digest,
        "verifier_receipt_digest": verifier_digest,
        "workspace_ref": workspace,
        "frontend_fingerprint": "sha256:frontend",
        "verifier_fingerprint": "sha256:verifier-package",
        "changed_files": [
            "app/app.js",
            "app/fixture_server.py",
            "app/index.html",
            "app/styles.css",
        ],
        "host_workspace_mutation_observed": True,
        "manual_mutation_detected": False,
        "alternate_producer_detected": False,
        "global_mutations": 0,
        "installed_frontend_patterns_mutations": 0,
        "host_load_observability": "HOST_LOAD_UNOBSERVABLE",
    }
    proof = {
        key: receipt[key]
        for key in (
            "status",
            "run_id",
            "artifact_digest",
            "browser_evidence_digest",
            "verifier_receipt_digest",
            "workspace_ref",
            "frontend_fingerprint",
            "verifier_fingerprint",
        )
    }
    check_ids = (
        *(f"P8-EVAL-{number:03d}" for number in range(11, 28)),
        *(f"P8-EVAL-{number:03d}" for number in range(29, 38)),
        *(f"P8-EVAL-{number:03d}" for number in range(39, 44)),
        "P8-EVAL-050",
        "P8-EVAL-053",
    )
    browser = {
        "status": "PASS",
        "composition_run": run,
        "artifact_digest": artifact,
        "summary": {"failed": 0},
        "checks": [
            {"id": check_id, "passed": True, "evidence": f"browser-018/{check_id}.json"}
            for check_id in check_ids
        ],
    }
    verifier = {
        "status": "PASS_WITH_LIMITATIONS",
        "composition_run": run,
        "receipt_digest": verifier_digest,
        "input": {
            "expected": {
                "artifact_digest": artifact,
                "browser_manifest_digest": browser_digest,
            },
        },
        "report": {"artifact_digest": artifact},
    }
    timeline = {
        "events": [
            {"event": event, "timestamp_ns": index, "run_id": run, "artifact_digest": artifact}
            for index, event in enumerate(
                (
                    "FRONTEND_HOST_MUTATION_COMPLETED",
                    "ARTIFACT_BUILD_COMPLETED",
                    "BROWSER_RUNTIME_COMPLETED",
                    "VERIFIER_HOST_COMPLETED",
                ),
                start=1,
            )
        ]
    }
    runtime = {
        "runtime_required": 33,
        "runtime_executed": 33,
        "runtime_passed": 33,
        "runtime_failed": 0,
        "runtime_blocked": 0,
        "promotion_relevant_unresolved": 0,
        "records": [
            {
                "id": check_id,
                "procedure": check_id,
                "execution_kind": "BROWSER_RUNTIME",
                "status": "PASS",
            }
            for check_id in check_ids
        ],
    }
    return receipt, proof, browser, verifier, timeline, runtime


def _valid_raw_chain() -> tuple[dict[str, Any], ...]:
    base = list(_valid_chain())
    receipt = base[0]
    receipt.update(
        {
            "authorization_id": "AUTH-current",
            "frontend_invocation_id": "INV-frontend",
            "verifier_invocation_id": "INV-verifier",
            "host_write_events": [
                {"sequence": 167, "path": "app/index.html"},
                {"sequence": 173, "path": "app/styles.css"},
                {"sequence": 183, "path": "app/app.js"},
                {"sequence": 193, "path": "app/fixture_server.py"},
                {"sequence": 203, "path": "app/styles.css"},
            ],
        }
    )
    changed = receipt["changed_files"]
    frontend_receipt = {
        "run_id": receipt["run_id"],
        "invocation_id": "INV-frontend",
        "authorization_id": "AUTH-current",
        "source": {"digest": receipt["artifact_digest"]},
        "workspace": {
            "changed_files": changed,
            "host_event_paths": changed,
            "manual_mutation_detected": False,
            "alternate_producer_detected": False,
        },
    }
    write_events = receipt["host_write_events"]
    frontend_events = {
        "events": [
            {
                "sequence": event["sequence"],
                "detail": f"tool=harness_write_file path={event['path']} bytes=1",
            }
            for event in write_events
        ]
    }
    observations = {
        f"evidence/file-{index:02d}.json": f"sha256:{index:064x}" for index in range(50)
    }
    verifier_receipt = {
        "status": "PASS_WITH_LIMITATIONS",
        "composition_run": receipt["run_id"],
        "invocation_id": "INV-verifier",
        "workspace": {"unchanged": True},
        "report_valid": True,
        "host": {"file_observations": observations},
        "report": {
            "inspected_file_digests": observations,
            "criteria": [{"id": "criterion", "status": "PASS"}],
        },
    }
    verifier_events = {
        "events": [
            {
                "sequence": index,
                "detail": f"tool=harness_hash_file path={path} bytes=1 sha256={digest}",
            }
            for index, (path, digest) in enumerate(observations.items(), start=1)
        ]
    }
    return (*base, frontend_receipt, frontend_events, verifier_receipt, verifier_events)


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


def test_manifest_validator_rejects_a_substituted_repository_entry(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    evidence_root = repository_root / "projects" / "codex-harness" / "evidence"
    source = repository_root / "projects" / "codex-harness" / "src" / "module.py"
    evidence_root.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    source.write_text("trusted = True\n", encoding="utf-8")
    relative = source.relative_to(repository_root).as_posix()
    manifest: dict[str, Any] = {
        "entries": [],
        "excluded_envelopes": [],
        "repository_entries": [
            {
                "path": relative,
                "bytes": source.stat().st_size,
                "sha256": "sha256:" + hashlib.sha256(b"substituted").hexdigest(),
            }
        ],
    }
    manifest["manifest_digest"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )

    errors = validate_review_manifest(manifest, evidence_root, repository_root)

    assert any("repository digest mismatch" in error for error in errors)


def test_validator_source_has_no_write_surface() -> None:
    source = Path(__file__).parents[3] / "scripts" / "validate_phase81_packet.py"
    text = source.read_text(encoding="utf-8")

    assert ".write_text(" not in text
    assert "mkdir(" not in text
    assert "unlink(" not in text


def test_valid_composition_chain_passes_attack_validator() -> None:
    assert validate_composition_chain(*_valid_chain()) == []


def test_valid_raw_producer_and_verifier_evidence_passes() -> None:
    assert validate_composition_chain(*_valid_raw_chain()) == []


def test_deleted_frontend_raw_write_event_invalidates_chain() -> None:
    records = list(copy.deepcopy(_valid_raw_chain()))
    records[7]["events"].pop()

    assert "FRONTEND_RAW_EVENT_BINDING_MISMATCH" in validate_composition_chain(*records)


def test_substituted_verifier_observation_invalidates_chain() -> None:
    records = list(copy.deepcopy(_valid_raw_chain()))
    records[9]["events"][0]["detail"] = records[9]["events"][0]["detail"].replace(
        "sha256:", "sha256:ff"
    )

    assert "VERIFIER_RAW_EVIDENCE_BINDING_MISMATCH" in validate_composition_chain(*records)


def test_verifier_write_surface_invalidates_chain() -> None:
    records = list(copy.deepcopy(_valid_raw_chain()))
    records[9]["events"].append({"detail": "tool=harness_write_file path=forbidden bytes=1"})

    assert "VERIFIER_RAW_EVIDENCE_BINDING_MISMATCH" in validate_composition_chain(*records)


@pytest.mark.parametrize(
    ("target", "mutation", "expected"),
    (
        (
            1,
            lambda record: record.__setitem__("frontend_fingerprint", "sha256:wrong"),
            "PROOF_FRONTEND_FINGERPRINT_MISMATCH",
        ),
        (
            1,
            lambda record: record.__setitem__("workspace_ref", "another/workspace"),
            "PROOF_WORKSPACE_REF_MISMATCH",
        ),
        (
            2,
            lambda record: record.__setitem__("composition_run", "P81-COMPOSE-OLD"),
            "BROWSER_RUN_OR_STATUS_MISMATCH",
        ),
        (
            3,
            lambda record: record["input"]["expected"].__setitem__(
                "artifact_digest", "sha256:other"
            ),
            "ARTIFACT_LINEAGE_MISMATCH",
        ),
        (
            2,
            lambda record: record.__setitem__("artifact_digest", "sha256:stale"),
            "ARTIFACT_LINEAGE_MISMATCH",
        ),
        (
            4,
            lambda record: record["events"][2].__setitem__("timestamp_ns", 1),
            "TIMELINE_NOT_STRICTLY_MONOTONIC",
        ),
        (
            0,
            lambda record: record.__setitem__("manual_mutation_detected", True),
            "MANUAL_MUTATION_DETECTED",
        ),
        (
            0,
            lambda record: record.__setitem__("alternate_producer_detected", True),
            "ALTERNATE_PRODUCER_DETECTED",
        ),
        (
            5,
            lambda record: record.__setitem__("runtime_executed", 0),
            "RUNTIME_EXECUTION_INCOMPLETE",
        ),
        (
            5,
            lambda record: record["records"][0].__setitem__("execution_kind", "STRUCTURAL"),
            "STRUCTURAL_RUNTIME_MISLABEL",
        ),
        (2, lambda record: record.__setitem__("summary", {"failed": 1}), "BROWSER_FAILURE_HIDDEN"),
        (
            2,
            lambda record: record["checks"][0].__setitem__("id", "functional.loading"),
            "REQUIRED_BROWSER_BEHAVIOR_MISSING",
        ),
        (
            5,
            lambda record: record["records"][0].__setitem__("procedure", "functional.loading"),
            "STRUCTURAL_RUNTIME_MISLABEL",
        ),
        (0, lambda record: record.__setitem__("global_mutations", 1), "GLOBAL_MUTATION_DETECTED"),
    ),
)
def test_composition_attack_invalidates_proof(
    target: int, mutation: Callable[[dict[str, Any]], None], expected: str
) -> None:
    records = list(copy.deepcopy(_valid_chain()))
    mutation(records[target])

    assert expected in validate_composition_chain(*records)


@pytest.mark.parametrize("status", sorted(ALLOWED_COMPOSITION_STATUSES))
def test_allowed_composition_statuses_are_explicit(status: str) -> None:
    assert validate_composition_status(status) == []
