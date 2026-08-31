#!/usr/bin/env python3
"""Generate an explicit authoritative-to-current Phase 7.3 coverage delta."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path


class CoverageDeltaError(ValueError):
    """Raised when coverage inventories cannot be reconciled safely."""


def build_delta(
    authoritative: Mapping[str, object],
    current: Mapping[str, object],
    *,
    coverage_artifact: str,
) -> dict[str, object]:
    """Return exact removed/added branch identities and derived risk counts."""

    authoritative_records = _records(authoritative, "branches")
    current_records = _records(current, "branches")
    authoritative_by_id = _index(authoritative_records, "authoritative")
    current_by_id = _index(current_records, "current")
    removed_ids = sorted(set(authoritative_by_id) - set(current_by_id))
    added_ids = sorted(set(current_by_id) - set(authoritative_by_id))

    return {
        "schema_version": "P7.3-COVERAGE-DELTA-RECONCILIATION-1",
        "phase": "PHASE7.3",
        "status": "RECONCILED",
        "authoritative_inventory": "evidence/phase-7.2/high-risk-branch-inventory.json",
        "final_inventory": "evidence/phase-7.3/medium-risk-inventory.json",
        "final_coverage": coverage_artifact,
        "counts": {
            "authoritative": _risk_counts(authoritative_records),
            "current": _risk_counts(current_records),
            "removed": len(removed_ids),
            "added": len(added_ids),
        },
        "removed_from_authoritative": [
            _delta_record(
                authoritative_by_id[branch_id],
                status="COVERED_BY_FINAL_FRESH_COVERAGE",
                evidence=[coverage_artifact],
            )
            for branch_id in removed_ids
        ],
        "added_to_authoritative": [
            _delta_record(
                current_by_id[branch_id],
                status="NEW_RESIDUAL_IN_FINAL_FRESH_COVERAGE",
                evidence=[coverage_artifact],
            )
            for branch_id in added_ids
        ],
        "reconciliation_rule": (
            "The current inventory is regenerated from the final fresh branch-aware coverage "
            "artifact. Removed and added records are listed by exact branch identity; no branch "
            "is silently renamed, dropped, or inferred from prose."
        ),
    }


def generate_output(
    authoritative_path: Path,
    current_path: Path,
    coverage_artifact: str,
    output_path: Path,
) -> dict[str, object]:
    authoritative = _load(authoritative_path)
    current = _load(current_path)
    delta = build_delta(
        authoritative,
        current,
        coverage_artifact=coverage_artifact,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(delta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return delta


def render_markdown(delta: Mapping[str, object]) -> str:
    removed = _records(delta, "removed_from_authoritative")
    added = _records(delta, "added_to_authoritative")
    counts = delta.get("counts")
    if not isinstance(counts, Mapping):
        raise CoverageDeltaError("delta counts are missing")
    lines = [
        "# Phase 7.3 Coverage Delta Reconciliation",
        "",
        "The authoritative Phase 7.2 branch set is compared with the final fresh",
        "coverage-derived Phase 7.3 branch set by exact branch identity.",
        "",
        f"- removed from authoritative residual set: {len(removed)}",
        f"- added to authoritative residual set: {len(added)}",
        f"- authoritative counts: {json.dumps(counts.get('authoritative'), sort_keys=True)}",
        f"- current counts: {json.dumps(counts.get('current'), sort_keys=True)}",
        "",
        "## Removed records",
        "",
    ]
    lines.extend(_render_records(removed))
    lines.extend(("", "## Added records", ""))
    lines.extend(_render_records(added))
    lines.extend(
        (
            "",
            "A removed record means the exact branch is covered by the final fresh",
            "measurement; it does not erase its historical Phase 7.2 identity.",
            "",
        )
    )
    return "\n".join(lines)


def _render_records(records: Sequence[Mapping[str, object]]) -> list[str]:
    if not records:
        return ["No records.", ""]
    return [
        f"- {record['branch_id']} — {record['identity']} — {record['status']}" for record in records
    ] + [""]


def _delta_record(
    record: Mapping[str, object],
    *,
    status: str,
    evidence: list[str],
) -> dict[str, object]:
    function = record.get("function")
    if function == "":
        function = "<module>"
    return {
        "branch_id": _text(record, "branch_id"),
        "status": status,
        "identity": [
            _text(record, "file"),
            function,
            _positive_int(record, "source_line"),
            _text(record, "target"),
        ],
        "evidence": list(evidence),
    }


def _risk_counts(records: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts = Counter(_text(record, "risk_level") for record in records)
    return {
        "high": counts.get("high", 0),
        "medium": counts.get("medium", 0),
        "low": counts.get("low", 0),
        "total": len(records),
    }


def _records(value: Mapping[str, object], field: str) -> list[dict[str, object]]:
    records = value.get(field)
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise CoverageDeltaError(f"{field} must be a list of objects")
    return records


def _index(records: Sequence[Mapping[str, object]], label: str) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for record in records:
        branch_id = _text(record, "branch_id")
        if branch_id in result:
            raise CoverageDeltaError(f"{label} contains duplicate branch_id: {branch_id}")
        result[branch_id] = record
    return result


def _text(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CoverageDeltaError(f"{field} must be non-empty text")
    return value


def _positive_int(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CoverageDeltaError(f"{field} must be a positive integer")
    return value


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CoverageDeltaError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authoritative", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--coverage-artifact", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    try:
        delta = generate_output(
            args.authoritative,
            args.current,
            args.coverage_artifact,
            args.output_json,
        )
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(render_markdown(delta), encoding="utf-8")
    except (CoverageDeltaError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(delta["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
