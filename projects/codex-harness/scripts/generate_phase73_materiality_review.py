#!/usr/bin/env python3
"""Generate branch-local materiality evidence for Phase 7.3 High/Medium risks."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

PROMOTION_RELEVANT = frozenset(
    {
        "MATERIAL_PROMOTION_RELEVANT",
        "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE",
    }
)
NONMATERIAL = "NON_MATERIAL_DEFENSIVE"
REQUIRED_EXCLUDED_EFFECTS = (
    "authority",
    "evidence_integrity",
    "external_io",
    "filesystem",
    "persistence",
    "side_effect",
)
REVIEW_LEVELS = frozenset({"high", "medium"})


class MaterialityReviewError(ValueError):
    """Raised when branch-local materiality evidence is incomplete or inconsistent."""


def build_review(
    inventory: Mapping[str, object], decisions: Mapping[str, object]
) -> dict[str, object]:
    """Build a deterministic review record for every current High/Medium branch."""

    branches = _records(inventory, "branches")
    decision_map = _decision_map(decisions)
    selected = [branch for branch in branches if _text(branch, "risk_level") in REVIEW_LEVELS]
    selected_ids = {_text(branch, "branch_id") for branch in selected}
    unknown = sorted(set(decision_map) - selected_ids)
    if unknown:
        raise MaterialityReviewError(
            "decisions reference branches outside the High/Medium review: " + ", ".join(unknown)
        )

    records: list[dict[str, object]] = []
    for branch in sorted(selected, key=lambda item: _text(item, "branch_id")):
        branch_id = _text(branch, "branch_id")
        decision = decision_map.get(branch_id)
        if decision is None:
            raise MaterialityReviewError(f"missing materiality decision for {branch_id}")
        materiality = _text(branch, "materiality")
        closure_status = _text(branch, "closure_status")
        if (
            decision.get("materiality") != materiality
            or decision.get("closure_status") != closure_status
        ):
            raise MaterialityReviewError(f"decision for {branch_id} does not match inventory")
        evidence = _evidence(
            decision.get("existing_evidence", branch.get("existing_evidence")),
            branch_id,
        )
        decision_reason = _text(decision, "decision_reason")
        context = _source_context(branch)
        records.append(
            {
                "branch_id": branch_id,
                "risk_level": _text(branch, "risk_level"),
                "file": _text(branch, "file"),
                "function": _text(branch, "function"),
                "source_context": context,
                "materiality": materiality,
                "closure_status": closure_status,
                "decision_reason": decision_reason,
                "materiality_evidence": _materiality_evidence(
                    branch, materiality, closure_status, context
                ),
                "evidence": evidence,
            }
        )

    review = {
        "schema_version": "P7.3-MATERIALITY-REVIEW-1",
        "phase": "PHASE7.3",
        "status": "BRANCH_LOCAL_REVIEWABLE",
        "policy": {
            "scope": "every current High and Medium residual branch",
            "nonmaterial_rule": (
                "NON_MATERIAL_DEFENSIVE is permitted only when the exact branch target is "
                "defensive data validation/normalization and the review records no authority, "
                "evidence-integrity, external-I/O, filesystem, persistence, or side effect."
            ),
            "coverage_disclaimer": (
                "Materiality evidence classifies promotion effect; it does not claim that "
                "the exact coverage arc was directly executed."
            ),
        },
        "summary": _summary(records),
        "records": records,
    }
    validate_review(review)
    return review


def validate_review(review: Mapping[str, object]) -> None:
    """Validate branch-local source context, materiality basis, and count summary."""

    records = _records(review, "records")
    ids: set[str] = set()
    for position, record in enumerate(records):
        branch_id = _text(record, "branch_id", position)
        if branch_id in ids:
            raise MaterialityReviewError(f"duplicate review branch_id: {branch_id}")
        ids.add(branch_id)
        risk_level = _text(record, "risk_level", position)
        if risk_level not in REVIEW_LEVELS:
            raise MaterialityReviewError(f"review record {branch_id} has invalid risk level")
        materiality = _text(record, "materiality", position)
        closure_status = _text(record, "closure_status", position)
        _text(record, "decision_reason", position)
        _evidence(record.get("evidence"), branch_id)
        context = record.get("source_context")
        if not isinstance(context, Mapping):
            raise MaterialityReviewError(f"source_context is missing for {branch_id}")
        for field in ("file", "function", "condition", "target"):
            _text(context, field, branch_id)
        for field in ("source_line", "target_line"):
            value = context.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value == 0:
                raise MaterialityReviewError(f"source_context {field} is invalid for {branch_id}")
        evidence = record.get("materiality_evidence")
        if not isinstance(evidence, Mapping):
            raise MaterialityReviewError(f"materiality_evidence is missing for {branch_id}")
        if evidence.get("classification") != materiality:
            raise MaterialityReviewError(f"materiality classification drifts for {branch_id}")
        reason = evidence.get("branch_local_reason")
        if not isinstance(reason, str) or branch_id not in reason or context["file"] not in reason:
            raise MaterialityReviewError(f"branch-local reason is incomplete for {branch_id}")
        if materiality == NONMATERIAL:
            effects = evidence.get("excluded_effects")
            if not isinstance(effects, list) or tuple(effects) != REQUIRED_EXCLUDED_EFFECTS:
                raise MaterialityReviewError(f"excluded_effects are incomplete for {branch_id}")
            if closure_status != "ACCEPTED_NON_MATERIAL":
                raise MaterialityReviewError(
                    f"non-material branch has incompatible closure for {branch_id}"
                )
        elif materiality in PROMOTION_RELEVANT or materiality == "UNREACHABLE_BY_CONTRACT":
            basis = evidence.get("closure_basis")
            if not isinstance(basis, str) or not basis.strip():
                raise MaterialityReviewError(f"closure_basis is missing for {branch_id}")
        else:
            raise MaterialityReviewError(f"unsupported materiality in review: {materiality}")

    expected = _summary(records)
    if review.get("summary") != expected:
        raise MaterialityReviewError("materiality review summary is not record-derived")


def generate_outputs(
    inventory_path: Path,
    decisions_path: Path,
    output_json: Path,
    output_markdown: Path,
) -> dict[str, object]:
    inventory = _load(inventory_path)
    decisions = _load(decisions_path)
    review = build_review(inventory, decisions)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_markdown.write_text(render_markdown(review), encoding="utf-8")
    return review


def render_markdown(review: Mapping[str, object]) -> str:
    validate_review(review)
    records = _records(review, "records")
    summary = review["summary"]
    lines = [
        "# Phase 7.3 Branch-Local Materiality Review",
        "",
        "This artifact is authoritative for the High/Medium branch-local materiality assessment.",
        "It preserves exact source context and separates non-material defensive acceptance from",
        "promotion-relevant closure evidence.",
        "",
        f"- records: {len(records)}",
        f"- summary: {json.dumps(summary, sort_keys=True)}",
        "",
        "| Branch ID | Risk | Source | Target | Materiality | Closure |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        context = record["source_context"]
        assert isinstance(context, Mapping)
        lines.append(
            "| {} | {} | {}:{}:{} | {} | {} | {} |".format(
                record["branch_id"],
                record["risk_level"],
                context["file"],
                context["function"],
                context["source_line"],
                context["target"],
                record["materiality"],
                record["closure_status"],
            )
        )
    return "\n".join(lines) + "\n"


def _materiality_evidence(
    branch: Mapping[str, object],
    materiality: str,
    closure_status: str,
    context: Mapping[str, object],
) -> dict[str, object]:
    branch_id = _text(branch, "branch_id")
    source = f"{context['file']}:{context['function']}:{context['source_line']}"
    target = str(context["target"])
    if materiality == NONMATERIAL:
        return {
            "classification": materiality,
            "excluded_effects": list(REQUIRED_EXCLUDED_EFFECTS),
            "branch_local_reason": (
                f"{branch_id} at {source} evaluates {context['condition']!r} and reaches "
                f"{target!r}; the target is bounded defensive validation/normalization with "
                "no authority, evidence-integrity, external-I/O, filesystem, persistence, "
                "or side-effect capability."
            ),
        }
    if materiality == "UNREACHABLE_BY_CONTRACT":
        basis = "The bounded contract makes the exact condition unreachable before this target."
    elif materiality == "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE":
        basis = (
            "The branch affects a promotion-relevant contract boundary; closure relies on the "
            "listed behavioral/regression evidence and keeps the residual arc visible."
        )
    else:
        basis = (
            "The branch affects a promotion-relevant contract boundary and remains actionable "
            f"under closure state {closure_status}."
        )
    return {
        "classification": materiality,
        "closure_basis": basis,
        "branch_local_reason": f"{branch_id} at {source} reaches {target!r}; {basis}",
    }


def _source_context(branch: Mapping[str, object]) -> dict[str, object]:
    source_line = _positive_int(branch, "source_line")
    target_line = branch.get("target_line", source_line + 1)
    if not isinstance(target_line, int) or isinstance(target_line, bool) or target_line == 0:
        raise MaterialityReviewError(f"target_line is invalid for {_text(branch, 'branch_id')}")
    condition = branch.get("condition", branch.get("closure_requirement"))
    if not isinstance(condition, str) or not condition.strip():
        raise MaterialityReviewError(f"condition is missing for {_text(branch, 'branch_id')}")
    return {
        "file": _text(branch, "file"),
        "function": _text(branch, "function"),
        "source_line": source_line,
        "target_line": target_line,
        "condition": condition,
        "target": _text(branch, "branch_target"),
    }


def _summary(records: Sequence[Mapping[str, object]]) -> dict[str, int]:
    risk_counts = Counter(str(record["risk_level"]) for record in records)
    return {
        "high": risk_counts.get("high", 0),
        "medium": risk_counts.get("medium", 0),
        "records": len(records),
        "accepted_nonmaterial": sum(
            1 for record in records if record["materiality"] == NONMATERIAL
        ),
        "promotion_relevant": sum(
            1 for record in records if record["materiality"] in PROMOTION_RELEVANT
        ),
    }


def _decision_map(value: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = value.get("decisions", value)
    if not isinstance(raw, Mapping):
        raise MaterialityReviewError("decisions must be a keyed object")
    result: dict[str, Mapping[str, object]] = {}
    for branch_id, decision in raw.items():
        if (
            not isinstance(branch_id, str)
            or not branch_id.strip()
            or not isinstance(decision, Mapping)
        ):
            raise MaterialityReviewError("decisions contain an invalid branch entry")
        result[branch_id] = decision
    return result


def _records(value: Mapping[str, object], field: str) -> list[dict[str, object]]:
    records = value.get(field)
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise MaterialityReviewError(f"{field} must be a list of objects")
    return records


def _evidence(value: object, branch_id: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise MaterialityReviewError(f"evidence is missing for {branch_id}")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise MaterialityReviewError(f"evidence is invalid for {branch_id}")
    return list(value)


def _text(record: Mapping[str, object], field: str, position: object = "record") -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise MaterialityReviewError(f"{field} must be non-empty text for {position}")
    return value


def _positive_int(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MaterialityReviewError(f"{field} must be a positive integer")
    return value


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MaterialityReviewError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-json", type=Path, required=True)
    parser.add_argument("--decisions-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    try:
        review = generate_outputs(
            args.inventory_json,
            args.decisions_json,
            args.output_json,
            args.output_markdown,
        )
    except (MaterialityReviewError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(review["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
