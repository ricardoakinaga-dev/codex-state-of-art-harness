#!/usr/bin/env python3
"""Generate current Phase 7.3 traceability with explicit targeted evidence overlays."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from generate_phase72_traceability import (  # noqa: E402
    _load_object,
    build_traceability,
)

BEHAVIORAL_MAPPING = "BEHAVIORAL_TARGETED_OR_REGRESSION"
RESIDUAL_COVERAGE = "RESIDUAL_BRANCH_NOT_DIRECTLY_COVERED"


class TraceabilityEvidenceError(ValueError):
    """Raised when a Phase 7.3 traceability overlay is not safely bound."""


def apply_phase73_evidence(
    traceability: Mapping[str, object],
    overlay: Mapping[str, object],
) -> dict[str, object]:
    """Apply targeted behavioral evidence to exact existing branch records."""

    records = _records(traceability, "records")
    evidence_records = _records(overlay, "records")
    by_id = _index(records, "traceability")
    overlay_by_id = _index(evidence_records, "overlay")
    unknown = sorted(set(overlay_by_id) - set(by_id))
    if unknown:
        raise TraceabilityEvidenceError(
            "overlay references unknown branch_id(s): " + ", ".join(unknown)
        )

    updated: list[dict[str, object]] = []
    for record in records:
        branch_id = _text(record, "branch_id")
        evidence = overlay_by_id.get(branch_id)
        if evidence is None:
            updated.append(dict(record))
            continue
        if record.get("tests"):
            raise TraceabilityEvidenceError(
                f"overlay may only bind an un-mapped residual branch: {branch_id}"
            )
        tests = evidence.get("tests")
        if not isinstance(tests, list) or not tests:
            raise TraceabilityEvidenceError(f"overlay tests are missing for {branch_id}")
        if evidence.get("mapping_strength") != BEHAVIORAL_MAPPING:
            raise TraceabilityEvidenceError(
                f"overlay mapping strength is not behavioral for {branch_id}"
            )
        if evidence.get("test_result") != "PASS":
            raise TraceabilityEvidenceError(f"overlay test result is not PASS for {branch_id}")
        normalized_tests = [_test_reference(item, branch_id) for item in tests]
        note = evidence.get("evidence_note")
        if not isinstance(note, str) or not note.strip():
            raise TraceabilityEvidenceError(f"overlay evidence_note is missing for {branch_id}")
        item = dict(record)
        item["tests"] = normalized_tests
        item["mapping_strength"] = BEHAVIORAL_MAPPING
        item["test_result"] = "PASS"
        item["coverage_result"] = RESIDUAL_COVERAGE
        item["phase73_evidence"] = [note]
        updated.append(item)

    result = dict(traceability)
    result["schema_version"] = "P7.3-BRANCH-TEST-TRACEABILITY-1"
    result["phase"] = "PHASE7.3"
    result["feature_freeze"] = "P7_3_FEATURE_FREEZE"
    result["records"] = updated
    result["summary"] = _summary(updated)
    result["interpretation"] = {
        "test_result": "The referenced test or regression suite passed when marked PASS.",
        "coverage_result": (
            "The exact source-to-target arc remains absent from fresh coverage even when "
            "targeted behavioral evidence is attached."
        ),
        "overlay_policy": (
            "The Phase 7.3 overlay can bind only an exact current residual branch with "
            "passing behavioral evidence; it never changes the coverage result to covered."
        ),
    }
    return result


def generate_outputs(
    inventory_path: Path,
    catalog_path: Path,
    overlay_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    inventory = _load_object(inventory_path)
    catalog_payload = _load_object(catalog_path)
    overlay = _load_object(overlay_path)
    catalog = _catalog(catalog_payload)
    traceability = build_traceability(inventory, catalog)
    result = apply_phase73_evidence(traceability, overlay)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "branch-test-traceability.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "branch-test-traceability.md").write_text(
        render_markdown(result),
        encoding="utf-8",
    )
    return result


def render_markdown(traceability: Mapping[str, object]) -> str:
    records = _records(traceability, "records")
    summary = traceability.get("summary")
    if not isinstance(summary, Mapping):
        raise TraceabilityEvidenceError("traceability summary is missing")
    lines = [
        "# Phase 7.3 Current Branch-to-Test Traceability",
        "",
        "Every current residual branch is listed. Targeted evidence overlays bind exact",
        "branch IDs while preserving the residual coverage result.",
        "",
        f"- residual branches: {len(records)}",
        f"- summary: {json.dumps(summary, sort_keys=True)}",
        "",
        "| Branch ID | Source | Risk | Mapping | Test result | Coverage |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        location = record.get("location")
        if not isinstance(location, Mapping):
            raise TraceabilityEvidenceError(
                f"traceability location is missing for {record.get('branch_id')}"
            )
        lines.append(
            "| {} | {}:{}:{} | {} | {} | {} | {} |".format(
                record["branch_id"],
                location["file"],
                location["function"],
                location["source_line"],
                record["risk_level"],
                record["mapping_strength"],
                record["test_result"],
                record["coverage_result"],
            )
        )
    return "\n".join(lines) + "\n"


def _summary(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {
        "total_residual_branches": len(records),
        "risk_counts": dict(sorted(Counter(str(item["risk_level"]) for item in records).items())),
        "mapping_strength_counts": dict(
            sorted(Counter(str(item["mapping_strength"]) for item in records).items())
        ),
        "test_result_counts": dict(
            sorted(Counter(str(item["test_result"]) for item in records).items())
        ),
        "overlay_bound_branches": sum(1 for item in records if item.get("phase73_evidence")),
    }


def _catalog(value: Mapping[str, object]) -> dict[str, dict[str, object]]:
    tests = value.get("tests")
    if not isinstance(tests, list) or any(not isinstance(item, dict) for item in tests):
        raise TraceabilityEvidenceError("test catalog must contain a list of objects")
    result: dict[str, dict[str, object]] = {}
    for item in tests:
        test_id = item.get("id")
        if not isinstance(test_id, str) or not test_id.strip() or test_id in result:
            raise TraceabilityEvidenceError("test catalog IDs must be unique non-empty text")
        result[test_id] = item
    return result


def _test_reference(value: object, branch_id: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TraceabilityEvidenceError(f"overlay test is not an object for {branch_id}")
    for field in ("test_id", "path", "nodeid", "relation"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise TraceabilityEvidenceError(f"overlay test {field} is missing for {branch_id}")
    if value.get("result") != "PASS":
        raise TraceabilityEvidenceError(f"overlay test result is not PASS for {branch_id}")
    return {
        "test_id": value["test_id"],
        "path": value["path"],
        "nodeid": value["nodeid"],
        "result": "PASS",
        "relation": value["relation"],
    }


def _records(value: Mapping[str, object], field: str) -> list[dict[str, object]]:
    records = value.get(field)
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise TraceabilityEvidenceError(f"{field} must be a list of objects")
    return records


def _index(records: Sequence[Mapping[str, object]], label: str) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for record in records:
        branch_id = _text(record, "branch_id")
        if branch_id in result:
            raise TraceabilityEvidenceError(f"{label} has duplicate branch_id: {branch_id}")
        result[branch_id] = dict(record)
    return result


def _text(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TraceabilityEvidenceError(f"{field} must be non-empty text")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--test-catalog", type=Path, required=True)
    parser.add_argument("--phase73-evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = generate_outputs(
            args.inventory,
            args.test_catalog,
            args.phase73_evidence,
            args.output_dir,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
