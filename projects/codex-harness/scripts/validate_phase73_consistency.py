#!/usr/bin/env python3
"""Validate Phase 7.3 branch identity and cross-artifact risk counts."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from generate_phase73_materiality_review import MaterialityReviewError, validate_review
from phase73_risk_semantics import (
    COUNT_KEYS,
    RiskSemanticError,
    semantic_counts,
    validate_count_consistency,
    validate_inventory_records,
)


class ConsistencyError(ValueError):
    """Raised when Phase 7.3 evidence surfaces disagree."""


def validate_consistency(
    *,
    phase72_inventory: Path,
    phase72_traceability: Path,
    phase73_inventory: Path,
    readiness: Path,
    ledger: Path,
    final_report: Path,
    authoritative_phase72_inventory: Path | None = None,
    coverage_delta: Path | None = None,
    material_proof: Path | None = None,
    materiality_review: Path | None = None,
) -> dict[str, object]:
    """Validate branch identity, record semantics, and every published count surface."""

    previous = _load_object(phase72_inventory)
    traceability = _load_object(phase72_traceability)
    current = _load_object(phase73_inventory)
    readiness_data = _load_object(readiness)
    ledger_data = _load_object(ledger)

    previous_branches = _records(previous, "branches", phase72_inventory)
    trace_records = _records(traceability, "records", phase72_traceability)
    current_branches = _records(current, "branches", phase73_inventory)
    authority_counts: dict[str, int] | None = None
    if authoritative_phase72_inventory is not None:
        authoritative = _load_object(authoritative_phase72_inventory)
        authoritative_branches = _records(
            authoritative,
            "branches",
            authoritative_phase72_inventory,
        )
        authority_counts = _validate_authority_reconciliation(
            authoritative_branches,
            previous_branches,
            coverage_delta,
        )
    previous_ids = _unique_ids(previous_branches, "Phase 7.2 inventory")
    trace_ids = _unique_ids(trace_records, "Phase 7.2 traceability")
    current_ids = _unique_ids(current_branches, "Phase 7.3 inventory")
    if previous_ids != trace_ids:
        raise ConsistencyError("Phase 7.2 branch set differs between inventory and traceability")
    if previous_ids != current_ids:
        raise ConsistencyError("Phase 7.3 branch set differs from Phase 7.2 inventory")
    _validate_identity(previous_branches, current_branches)

    validate_inventory_records(current_branches)
    materiality_review_summary = _validate_materiality_review(
        current_branches,
        materiality_review,
    )
    material_proof_counts = _validate_material_proof(current_branches, material_proof)
    derived = semantic_counts(current_branches)
    declared_semantic = _count_surface(current, "semantic_counts", "Phase 7.3 inventory")
    if declared_semantic != derived:
        raise ConsistencyError("Phase 7.3 inventory semantic_counts are not record-derived")

    declared_risk = _risk_counts(current, "Phase 7.3 inventory")
    observed_risk = Counter(str(record["risk_level"]) for record in current_branches)
    derived_risk = {key: observed_risk.get(key, 0) for key in ("high", "medium", "low")}
    if declared_risk != derived_risk:
        raise ConsistencyError("Phase 7.3 inventory risk_counts are not record-derived")

    previous_risk = _risk_counts(previous, "Phase 7.2 inventory")
    if previous_risk != declared_risk:
        raise ConsistencyError("Phase 7.2 and Phase 7.3 risk counts differ")

    readiness_counts = _count_surface(readiness_data, "risk_counts", "readiness")
    ledger_counts = _count_surface(ledger_data, "semantic_counts", "promotion ledger")
    report_counts = _extract_report_counts(final_report)
    try:
        validate_count_consistency(
            inventory=declared_semantic,
            readiness=readiness_counts,
            ledger=ledger_counts,
            report=report_counts,
        )
    except RiskSemanticError as exc:
        raise ConsistencyError(f"count surface consistency failure: {exc}") from exc

    return {
        "schema_version": "P7.3-RISK-COUNT-CONSISTENCY-1",
        "phase": "PHASE7.3",
        "status": "PASS",
        "branch_set_consistent": True,
        "count_surfaces_consistent": True,
        "branch_counts": {
            "phase72_inventory": len(previous_ids),
            "phase72_traceability": len(trace_ids),
            "phase73_inventory": len(current_ids),
        },
        "risk_counts": declared_risk,
        "semantic_counts": declared_semantic,
        "authority_reconciliation": authority_counts,
        "material_proof": material_proof_counts,
        "materiality_review": materiality_review_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase72-inventory", type=Path, required=True)
    parser.add_argument("--phase72-traceability", type=Path, required=True)
    parser.add_argument("--phase73-inventory", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--final-report", type=Path, required=True)
    parser.add_argument("--phase72-authoritative-inventory", type=Path)
    parser.add_argument("--coverage-delta", type=Path)
    parser.add_argument("--material-proof", type=Path)
    parser.add_argument("--materiality-review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = validate_consistency(
            phase72_inventory=args.phase72_inventory,
            phase72_traceability=args.phase72_traceability,
            phase73_inventory=args.phase73_inventory,
            readiness=args.readiness,
            ledger=args.ledger,
            final_report=args.final_report,
            authoritative_phase72_inventory=args.phase72_authoritative_inventory,
            coverage_delta=args.coverage_delta,
            material_proof=args.material_proof,
            materiality_review=args.materiality_review,
        )
    except (ConsistencyError, OSError, TypeError, ValueError) as exc:
        report = {
            "schema_version": "P7.3-RISK-COUNT-CONSISTENCY-1",
            "phase": "PHASE7.3",
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, sort_keys=True))
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "risk_counts": report["risk_counts"]}))
    return 0


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConsistencyError(f"{path} must contain an object")
    return value


def _records(payload: Mapping[str, object], field: str, path: Path) -> list[dict[str, Any]]:
    value = payload.get(field)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ConsistencyError(f"{path} field {field} must be a list of objects")
    return value


def _unique_ids(records: Sequence[Mapping[str, object]], label: str) -> set[str]:
    result: set[str] = set()
    for position, record in enumerate(records):
        branch_id = record.get("branch_id")
        if not isinstance(branch_id, str) or not branch_id:
            raise ConsistencyError(f"{label} record {position} has no valid branch_id")
        if branch_id in result:
            raise ConsistencyError(f"{label} contains duplicate branch_id: {branch_id}")
        result.add(branch_id)
    return result


def _validate_identity(
    previous: Sequence[Mapping[str, object]], current: Sequence[Mapping[str, object]]
) -> None:
    old_by_id = {str(record["branch_id"]): record for record in previous}
    new_by_id = {str(record["branch_id"]): record for record in current}
    for branch_id in sorted(old_by_id):
        old = old_by_id[branch_id]
        new = new_by_id[branch_id]
        old_identity = _identity(old, "target")
        new_identity = _identity(new, "branch_target")
        if old_identity != new_identity:
            raise ConsistencyError(f"branch identity drift for {branch_id}")


def _identity(record: Mapping[str, object], target_field: str) -> tuple[object, ...]:
    function = record.get("function")
    if function == "":
        function = "<module>"
    return (
        record.get("file"),
        function,
        record.get("source_line"),
        record.get(target_field),
    )


def _validate_authority_reconciliation(
    authoritative: Sequence[Mapping[str, object]],
    current: Sequence[Mapping[str, object]],
    delta_path: Path | None,
) -> dict[str, int]:
    """Require every authoritative/current branch-set delta to be evidenced."""

    authoritative_by_id = {
        str(record["branch_id"]): record for record in authoritative if "branch_id" in record
    }

    current_by_id = {
        str(record["branch_id"]): record for record in current if "branch_id" in record
    }
    removed_ids = sorted(set(authoritative_by_id) - set(current_by_id))
    added_ids = sorted(set(current_by_id) - set(authoritative_by_id))
    if delta_path is None:
        if removed_ids or added_ids:
            raise ConsistencyError("authority/current branch-set delta requires reconciliation")
        return {"authoritative": len(authoritative_by_id), "current": len(current_by_id)}

    delta = _load_object(delta_path)
    removed_items = _delta_records(delta.get("removed_from_authoritative"), "removed")
    added_items = _delta_records(delta.get("added_to_authoritative"), "added")
    declared_removed = _delta_ids(removed_items)
    declared_added = _delta_ids(added_items)
    if declared_removed != set(removed_ids) or declared_added != set(added_ids):
        raise ConsistencyError(
            "authority reconciliation does not match the observed branch-set delta"
        )
    for item in removed_items:
        _validate_delta_record(
            item,
            authoritative_by_id[item["branch_id"]],
            expected_status="COVERED_BY_FINAL_FRESH_COVERAGE",
            target_field="target",
        )
    for item in added_items:
        _validate_delta_record(
            item,
            current_by_id[item["branch_id"]],
            expected_status="NEW_RESIDUAL_IN_FINAL_FRESH_COVERAGE",
            target_field="target",
        )
    return {
        "authoritative": len(authoritative_by_id),
        "current": len(current_by_id),
        "removed_from_authoritative": len(removed_ids),
        "added_to_authoritative": len(added_ids),
    }


def _validate_materiality_review(
    current: Sequence[Mapping[str, object]], review_path: Path | None
) -> dict[str, int] | None:
    """Bind the branch-local materiality artifact to current source identities."""

    if review_path is None:
        return None
    review = _load_object(review_path)
    try:
        validate_review(review)
    except MaterialityReviewError as exc:
        raise ConsistencyError(f"materiality review is invalid: {exc}") from exc
    review_records = _records(review, "records", review_path)
    expected = {
        str(record["branch_id"])
        for record in current
        if record.get("risk_level") in {"high", "medium"}
    }
    observed = _unique_ids(review_records, "materiality review")
    if observed != expected:
        raise ConsistencyError("materiality review branch set differs from current inventory")
    current_by_id = {str(record["branch_id"]): record for record in current}
    for review_record in review_records:
        branch_id = str(review_record["branch_id"])
        source = current_by_id[branch_id]
        if review_record.get("materiality") != source.get("materiality") or review_record.get(
            "closure_status"
        ) != source.get("closure_status"):
            raise ConsistencyError(f"materiality review semantics drift for {branch_id}")
        context = review_record.get("source_context")
        if not isinstance(context, Mapping):
            raise ConsistencyError(f"materiality review source context is missing for {branch_id}")
        expected_target_line = source.get("target_line", int(source["source_line"]) + 1)
        expected_condition = source.get("condition", source["closure_requirement"])
        if (
            context.get("file") != source.get("file")
            or context.get("function") != source.get("function")
            or context.get("source_line") != source.get("source_line")
            or context.get("target_line") != expected_target_line
            or context.get("condition") != expected_condition
            or context.get("target") != source.get("branch_target")
        ):
            raise ConsistencyError(f"materiality review source identity drift for {branch_id}")
    summary = review.get("summary")
    if not isinstance(summary, Mapping):
        raise ConsistencyError("materiality review summary is missing")
    return {
        key: _non_negative_count(summary, key, "materiality review")
        for key in ("records", "high", "medium", "accepted_nonmaterial", "promotion_relevant")
    }


def _non_negative_count(value: Mapping[str, object], key: str, label: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise ConsistencyError(f"{label} count {key} is invalid")
    return item


def _validate_material_proof(
    current: Sequence[Mapping[str, object]], proof_path: Path | None
) -> dict[str, int]:
    """Require a separately reviewable record for every material Medium branch."""

    material = {
        str(record["branch_id"]): record
        for record in current
        if record.get("risk_level") == "medium"
        and record.get("materiality") == "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE"
    }
    if not material:
        return {"required": 0, "reviewable": 0}
    if proof_path is None:
        raise ConsistencyError("material proof is required for material Medium branches")

    proof = _load_object(proof_path)
    proof_records = _records(proof, "records", proof_path)
    proof_ids = _unique_ids(proof_records, "material proof")
    if proof_ids != set(material):
        raise ConsistencyError("material proof branch set differs from material Medium inventory")

    for item in proof_records:
        branch_id = str(item["branch_id"])
        source = material[branch_id]
        if item.get("proof_status") != "REVIEWABLE":
            raise ConsistencyError(f"material proof is not reviewable for {branch_id}")
        if item.get("exact_arc_direct_execution") is not False:
            raise ConsistencyError(f"material proof has invalid coverage claim for {branch_id}")
        for field in ("file", "function", "source_line", "branch_target", "category"):
            if item.get(field) != source.get(field):
                raise ConsistencyError(f"material proof identity differs for {branch_id}")
        context = item.get("source_context")
        if not isinstance(context, Mapping):
            raise ConsistencyError(f"material proof source context is missing for {branch_id}")
        if context.get("target") != source.get("branch_target"):
            raise ConsistencyError(f"material proof target differs for {branch_id}")
        if not isinstance(context.get("condition"), str) or not context["condition"].strip():
            raise ConsistencyError(f"material proof condition is missing for {branch_id}")
        if not _is_non_zero_int(context.get("target_line")):
            raise ConsistencyError(f"material proof target line is invalid for {branch_id}")
        tests = item.get("prior_contract_tests")
        if not isinstance(tests, list) or any(not isinstance(test, Mapping) for test in tests):
            raise ConsistencyError(f"material proof test references are invalid for {branch_id}")
        trace = item.get("prior_traceability")
        if not isinstance(trace, Mapping):
            raise ConsistencyError(f"material proof traceability is missing for {branch_id}")
        for field in ("mapping_strength", "test_result", "coverage_result"):
            if not isinstance(trace.get(field), str) or not trace[field].strip():
                raise ConsistencyError(f"material proof traceability is incomplete for {branch_id}")
        if trace.get("mapping_strength") != "BEHAVIORAL_TARGETED_OR_REGRESSION":
            raise ConsistencyError(f"material proof lacks behavioral evidence for {branch_id}")
        if trace.get("test_result") != "PASS":
            raise ConsistencyError(f"material proof test result is not PASS for {branch_id}")
        if not tests:
            raise ConsistencyError(
                f"material proof lacks behavioral test references for {branch_id}"
            )
        for test in tests:
            if (
                not isinstance(test.get("test_id"), str)
                or not test["test_id"].strip()
                or not isinstance(test.get("path"), str)
                or not test["path"].strip()
                or test.get("result") != "PASS"
            ):
                raise ConsistencyError(
                    f"material proof contains an invalid behavioral test for {branch_id}"
                )
        evidence = item.get("proof_evidence")
        if not isinstance(evidence, list) or any(
            not isinstance(value, str) or not value.strip() for value in evidence
        ):
            raise ConsistencyError(f"material proof evidence is missing for {branch_id}")
        for field in ("proof_type", "proof_statement", "source_record_digest"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ConsistencyError(f"material proof {field} is missing for {branch_id}")
    return {"required": len(material), "reviewable": len(proof_records)}


def _delta_records(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ConsistencyError(f"authority reconciliation {label} must be a list of objects")
    return value


def _is_non_zero_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value != 0


def _delta_ids(records: Sequence[Mapping[str, object]]) -> set[str]:
    result: set[str] = set()
    for record in records:
        branch_id = record.get("branch_id")
        if not isinstance(branch_id, str) or not branch_id:
            raise ConsistencyError("authority reconciliation has an invalid branch_id")
        result.add(branch_id)
    return result


def _validate_delta_record(
    item: Mapping[str, object],
    source: Mapping[str, object],
    *,
    expected_status: str,
    target_field: str,
) -> None:
    branch_id = item.get("branch_id")
    if branch_id != source.get("branch_id"):
        raise ConsistencyError("authority reconciliation branch_id is invalid")
    if item.get("status") != expected_status:
        raise ConsistencyError(f"authority reconciliation status is not {expected_status}")
    if item.get("identity") != list(_identity(source, target_field)):
        raise ConsistencyError(f"authority reconciliation identity is invalid for {branch_id}")
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or any(
        not isinstance(value, str) or not value for value in evidence
    ):
        raise ConsistencyError(f"authority reconciliation evidence is missing for {branch_id}")


def _risk_counts(payload: Mapping[str, object], label: str) -> dict[str, int]:
    value = payload.get("risk_counts")
    if not isinstance(value, Mapping):
        raise ConsistencyError(f"{label} has no risk_counts object")
    result = {key: value.get(key, 0) for key in ("high", "medium", "low")}
    if any(
        not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in result.values()
    ):
        raise ConsistencyError(f"{label} risk_counts contain invalid values")
    return result


def _count_surface(payload: Mapping[str, object], field: str, label: str) -> dict[str, int]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise ConsistencyError(f"{label} has no {field} object")
    missing = [key for key in COUNT_KEYS if key not in value]
    if missing:
        raise ConsistencyError(f"{label} {field} is missing: {', '.join(missing)}")
    return {key: value[key] for key in COUNT_KEYS}


def _extract_report_counts(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"<!--\s*PHASE73_SEMANTIC_COUNTS_START\s*-->\s*"
        r"(?P<json>\{.*?\})\s*"
        r"<!--\s*PHASE73_SEMANTIC_COUNTS_END\s*-->",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise ConsistencyError("final report has no fixed Phase 7.3 semantic count block")
    value = json.loads(match.group("json"))
    if not isinstance(value, dict):
        raise ConsistencyError("final report semantic count block must be an object")
    return _count_surface({"semantic_counts": value}, "semantic_counts", "final report")


if __name__ == "__main__":
    raise SystemExit(main())
