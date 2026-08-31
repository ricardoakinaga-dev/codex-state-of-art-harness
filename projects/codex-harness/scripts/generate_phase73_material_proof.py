#!/usr/bin/env python3
"""Build a branch-by-branch, separately reviewable proof matrix for material Medium risks."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

MATERIALITY = "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE"
PROOF_STATUS = "REVIEWABLE"
BEHAVIORAL_MAPPING = "BEHAVIORAL_TARGETED_OR_REGRESSION"
SOURCE_EVIDENCE = (
    "evidence/phase-7.2/README.md",
    "evidence/phase-7.2/residual-risk-review.md",
)


class MaterialProofError(ValueError):
    """Raised when the proof matrix cannot be bound to the residual inventory."""


def build_proof(
    inventory: Mapping[str, object], traceability: Mapping[str, object]
) -> dict[str, object]:
    """Create one exact proof record for every material Medium residual."""

    branches = _records(inventory, "branches")
    traces = _records(traceability, "records")
    trace_by_id = _index(traces, "traceability")
    material = [
        branch
        for branch in branches
        if branch.get("risk_level") == "medium" and branch.get("materiality") == MATERIALITY
    ]
    proof_records: list[dict[str, object]] = []
    for branch in sorted(material, key=lambda item: _text(item, "branch_id")):
        branch_id = _text(branch, "branch_id")
        trace = trace_by_id.get(branch_id)
        if trace is None:
            raise MaterialProofError(f"material branch is missing traceability: {branch_id}")
        location = trace.get("location")
        if not isinstance(location, Mapping):
            raise MaterialProofError(f"traceability location is missing: {branch_id}")
        tests = trace.get("tests", [])
        if not isinstance(tests, list) or any(not isinstance(item, Mapping) for item in tests):
            raise MaterialProofError(f"traceability tests are invalid: {branch_id}")
        mapping_strength = _text(trace, "mapping_strength")
        if mapping_strength != BEHAVIORAL_MAPPING or not tests:
            raise MaterialProofError(f"material branch lacks behavioral evidence: {branch_id}")
        evidence = _evidence(branch, tests)
        proof_records.append(
            {
                "branch_id": branch_id,
                "file": _text(branch, "file"),
                "function": _text(branch, "function"),
                "source_line": _positive_int(branch, "source_line"),
                "branch_target": _text(branch, "branch_target"),
                "category": _text(branch, "category"),
                "closure_requirement": _text(branch, "closure_requirement"),
                "proof_type": "PRIOR_CONTRACT_EVIDENCE_REVIEW",
                "proof_status": PROOF_STATUS,
                "exact_arc_direct_execution": False,
                "source_context": {
                    "condition": _text(location, "condition"),
                    "target": _text(location, "target"),
                    "target_line": _coverage_line(location, "target_line"),
                },
                "prior_contract_tests": [dict(item) for item in tests],
                "prior_traceability": {
                    "mapping_strength": mapping_strength,
                    "test_result": _text(trace, "test_result"),
                    "coverage_result": _text(trace, "coverage_result"),
                },
                "proof_evidence": evidence,
                "proof_statement": _proof_statement(branch, trace),
                "source_record_digest": _record_digest(branch, location),
            }
        )

    mapping_counts = Counter(
        str(item["prior_traceability"]["mapping_strength"]) for item in proof_records
    )
    return {
        "schema_version": "P7.3-MATERIAL-MEDIUM-PROOF-1",
        "phase": "PHASE7.3",
        "status": "REVIEWABLE_PROOF_MATRIX",
        "materiality": MATERIALITY,
        "source_inventory": "evidence/phase-7.3/medium-risk-inventory.json",
        "source_traceability": (
            "evidence/phase-7.3/phase73-current/traceability/branch-test-traceability.json"
        ),
        "proof_policy": {
            "purpose": (
                "Bind each material Medium residual to its exact source condition and target, "
                "then expose the prior contract evidence for independent review."
            ),
            "coverage_disclaimer": (
                "A residual arc is not claimed as directly executed. The proof relies on the "
                "listed prior contract evidence and remains reviewable against source and tests."
            ),
            "required_record_fields": [
                "branch_id",
                "file",
                "function",
                "source_line",
                "branch_target",
                "source_context",
                "prior_contract_tests",
                "proof_evidence",
                "proof_statement",
            ],
        },
        "summary": {
            "material_medium_count": len(proof_records),
            "proof_record_count": len(proof_records),
            "mapping_strength_counts": dict(sorted(mapping_counts.items())),
            "exact_arc_direct_execution_count": sum(
                1 for item in proof_records if item["exact_arc_direct_execution"]
            ),
        },
        "records": proof_records,
    }


def generate_outputs(
    inventory_path: Path,
    traceability_path: Path,
    output_json: Path,
    output_markdown: Path,
) -> dict[str, object]:
    inventory = _load(inventory_path)
    traceability = _load(traceability_path)
    proof = build_proof(inventory, traceability)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(proof, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_markdown.write_text(render_markdown(proof), encoding="utf-8")
    return proof


def render_markdown(proof: Mapping[str, object]) -> str:
    records = _records(proof, "records")
    summary = proof.get("summary")
    if not isinstance(summary, Mapping):
        raise MaterialProofError("proof summary is missing")
    lines = [
        "# Phase 7.3 Material Medium Proof Matrix",
        "",
        "This matrix is the separately reviewable proof required for every",
        "`MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE` Medium residual.",
        "",
        f"- material Medium records: `{summary.get('material_medium_count')}`",
        f"- proof records: `{summary.get('proof_record_count')}`",
        "- exact arcs claimed directly executed: "
        f"`{summary.get('exact_arc_direct_execution_count')}`",
        "",
        "The exact residual arc remains visible. This matrix does not turn a",
        "neighboring test into branch coverage; it binds the source condition,",
        "target, prior traceability and contract evidence for independent review.",
        "",
        "## Records",
        "",
        "| Branch ID | Source | Target | Category | Mapping | Proof status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        context = record.get("source_context")
        trace = record.get("prior_traceability")
        if not isinstance(context, Mapping) or not isinstance(trace, Mapping):
            raise MaterialProofError("proof record context is invalid")
        lines.append(
            "| `{}` | `{}:{}` | `{}` | `{}` | `{}` | `{}` |".format(
                record.get("branch_id"),
                record.get("file"),
                record.get("source_line"),
                context.get("target"),
                record.get("category"),
                trace.get("mapping_strength"),
                record.get("proof_status"),
            )
        )
    return "\n".join(lines) + "\n"


def _proof_statement(branch: Mapping[str, object], trace: Mapping[str, object]) -> str:
    target = (
        _text(trace.get("location"), "target") if isinstance(trace.get("location"), Mapping) else ""
    )
    tests = trace.get("tests")
    test_count = len(tests) if isinstance(tests, list) else 0
    if "raise " in target:
        basis = "an explicit fail-closed validation or binding target"
    elif "return _result(" in target:
        basis = "a bounded verification result rather than a success path"
    elif "findings.append" in target:
        basis = "an explicit validation finding that prevents invalid state from being accepted"
    elif "blockers.append" in target:
        basis = "an explicit blocker that prevents capability use without required context"
    elif "events.append" in target:
        basis = "a bounded lifecycle event with no authority to create a successful result"
    elif "return FreshnessStatus" in target:
        basis = "an explicit freshness state rather than a fresh-success claim"
    else:
        basis = "a bounded normalization, binding, or optional-path operation"
    return (
        f"The exact residual target is {basis}. The source condition and target are bound above; "
        f"the Phase 7.2 traceability record supplies {test_count} prior contract test reference(s) "
        "and its invariant. Independent review must confirm that those assertions preserve the "
        "stated contract and do not rely on a false branch-coverage claim."
    )


def _evidence(branch: Mapping[str, object], tests: Sequence[Mapping[str, object]]) -> list[str]:
    values = list(SOURCE_EVIDENCE)
    branch_evidence = branch.get("existing_evidence", [])
    if isinstance(branch_evidence, Sequence) and not isinstance(branch_evidence, (str, bytes)):
        values.extend(str(item) for item in branch_evidence)
    values.extend(
        str(item["path"]) for item in tests if isinstance(item.get("path"), str) and item["path"]
    )
    return sorted(set(values))


def _record_digest(branch: Mapping[str, object], location: Mapping[str, object]) -> str:
    value = {
        "branch_id": branch.get("branch_id"),
        "file": branch.get("file"),
        "function": branch.get("function"),
        "source_line": branch.get("source_line"),
        "branch_target": branch.get("branch_target"),
        "condition": location.get("condition"),
        "target": location.get("target"),
        "target_line": location.get("target_line"),
    }
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MaterialProofError(f"{path} must contain an object")
    return value


def _records(payload: Mapping[str, object], field: str) -> list[dict[str, object]]:
    value = payload.get(field)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise MaterialProofError(f"{field} must be a list of objects")
    return value


def _index(records: Sequence[Mapping[str, object]], label: str) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for record in records:
        branch_id = _text(record, "branch_id")
        if branch_id in result:
            raise MaterialProofError(f"{label} contains duplicate branch_id: {branch_id}")
        result[branch_id] = dict(record)
    return result


def _text(record: Mapping[str, object] | object, field: str) -> str:
    if not isinstance(record, Mapping):
        raise MaterialProofError(f"{field} requires an object")
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise MaterialProofError(f"{field} must be non-empty text")
    return value


def _positive_int(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MaterialProofError(f"{field} must be a positive integer")
    return value


def _coverage_line(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value == 0:
        raise MaterialProofError(f"{field} must be a non-zero integer")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--traceability", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    try:
        proof = generate_outputs(
            args.inventory,
            args.traceability,
            args.output_json,
            args.output_markdown,
        )
    except (OSError, MaterialProofError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(proof["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
