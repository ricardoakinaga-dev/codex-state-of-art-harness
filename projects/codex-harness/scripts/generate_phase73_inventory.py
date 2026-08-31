#!/usr/bin/env python3
"""Generate the deterministic Phase 7.3 semantic residual inventory.

The Phase 7.2 inventory remains the authoritative source for branch identity and
location.  This generator only normalizes its record vocabulary and applies
explicit Phase 7.3 decisions where supplied.  Counts are always recalculated
from the generated records by :mod:`phase73_risk_semantics`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeGuard, cast

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from phase73_risk_semantics import (  # noqa: E402
    CLOSURE_STATES,
    MATERIALITIES,
    semantic_counts,
    validate_inventory_records,
)

OUTPUT_JSON_NAME = "medium-risk-inventory.json"
OUTPUT_MARKDOWN_NAME = "medium-risk-inventory.md"
PHASE73_SCHEMA_VERSION = "P7.3-SEMANTIC-RESIDUAL-INVENTORY-1"
PHASE73_FEATURE_FREEZE = "P7_3_FEATURE_FREEZE"
RISK_LEVELS = frozenset({"high", "medium", "low"})
FORBIDDEN_CLOSURE_STATUS = "DEFERRED_BLOCKING_PROMOTION"

Record = dict[str, object]
Inventory = dict[str, object]
DecisionMap = dict[str, Mapping[str, object]]


class InventoryGenerationError(ValueError):
    """Raised when a Phase 7.2 source or Phase 7.3 decision is invalid."""


def build_inventory(
    source_inventory: Mapping[str, object],
    decisions: object | None = None,
) -> Inventory:
    """Build a Phase 7.3 inventory from one Phase 7.2 inventory object.

    ``decisions`` may be a mapping keyed by ``branch_id``, a list of decision
    objects containing ``branch_id``, or an object containing either form under
    a ``decisions`` key.  A Medium source branch must have a decision that
    explicitly supplies both ``materiality`` and ``closure_status``.
    """

    _validate_source_phase(source_inventory)
    source_branches = _source_branches(source_inventory)
    decision_map = _normalize_decisions(decisions)
    source_ids = {
        _required_text(branch, "branch_id", index) for index, branch in enumerate(source_branches)
    }
    unknown_decisions = sorted(set(decision_map) - source_ids)
    if unknown_decisions:
        raise InventoryGenerationError(
            "decisions reference unknown branch_id(s): " + ", ".join(unknown_decisions)
        )

    records = [
        _convert_branch(branch, decision_map.get(_required_text(branch, "branch_id", index)), index)
        for index, branch in enumerate(source_branches)
    ]
    records = sorted(records, key=lambda record: cast(str, record["branch_id"]))

    try:
        validate_inventory_records(records)
        counts = semantic_counts(records)
    except ValueError as exc:
        raise InventoryGenerationError(str(exc)) from exc

    source_phase = source_inventory.get("phase", "PHASE7.2")
    source_schema = source_inventory.get("schema_version", "P7.2-HIGH-RISK-BRANCH-INVENTORY-1")
    if not isinstance(source_phase, str) or not source_phase.strip():
        raise InventoryGenerationError("source phase must be non-empty text")
    if not isinstance(source_schema, str) or not source_schema.strip():
        raise InventoryGenerationError("source schema_version must be non-empty text")

    return {
        "schema_version": PHASE73_SCHEMA_VERSION,
        "phase": "PHASE7.3",
        "feature_freeze": PHASE73_FEATURE_FREEZE,
        "source_phase": source_phase,
        "source_schema_version": source_schema,
        "branches": records,
        "risk_counts": _risk_counts(counts),
        "semantic_counts": counts,
        "valid_materialities": sorted(MATERIALITIES),
        "valid_closure_states": sorted(CLOSURE_STATES),
    }


def generate_outputs(
    inventory_json: str | Path,
    output_dir: str | Path,
    decisions_json: str | Path | None = None,
) -> Inventory:
    """Read input files and write the deterministic JSON and Markdown outputs."""

    source_path = Path(inventory_json)
    source_value = _read_json(source_path)
    if not isinstance(source_value, Mapping):
        raise InventoryGenerationError(f"{source_path} must contain a JSON object")

    decisions_value = None
    if decisions_json is not None:
        decisions_value = _read_json(Path(decisions_json))

    generated = build_inventory(source_value, decisions_value)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    _write_json(destination / OUTPUT_JSON_NAME, generated)
    (destination / OUTPUT_MARKDOWN_NAME).write_text(render_markdown(generated), encoding="utf-8")
    return generated


def render_markdown(inventory: Mapping[str, object]) -> str:
    """Render Markdown whose count surfaces are derived from its branch list."""

    records = _inventory_records(inventory)
    try:
        validate_inventory_records(records)
        counts = semantic_counts(records)
    except ValueError as exc:
        raise InventoryGenerationError(str(exc)) from exc

    lines = [
        "# Phase 7.3 Semantic Residual Inventory",
        "",
        "The JSON inventory is authoritative; every current Phase 7.2 residual "
        "branch is represented.",
        "",
        "## Semantic counts",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        *[f"| `{key}` | {counts[key]} |" for key in counts],
        "",
        "## Risk counts",
        "",
        "| Risk level | Count |",
        "| --- | ---: |",
        *[f"| `{risk_level}` | {counts[risk_level]} |" for risk_level in ("high", "medium", "low")],
        "",
        "## Residual records",
        "",
        "| Branch ID | File | Function | Line | Risk | Materiality | Closure status |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ]
    lines.extend(
        "| `{branch_id}` | `{file}` | `{function}` | {source_line} | `{risk_level}` | "
        "`{materiality}` | `{closure_status}` |".format(
            branch_id=_markdown_cell(record["branch_id"]),
            file=_markdown_cell(record["file"]),
            function=_markdown_cell(record["function"]),
            source_line=record["source_line"],
            risk_level=_markdown_cell(record["risk_level"]),
            materiality=_markdown_cell(record["materiality"]),
            closure_status=_markdown_cell(record["closure_status"]),
        )
        for record in sorted(records, key=lambda item: cast(str, item["branch_id"]))
    )
    return "\n".join(lines) + "\n"


def load_decisions(path: str | Path) -> DecisionMap:
    """Load and normalize a decision file without requiring package installation."""

    value = _read_json(Path(path))
    normalized = _normalize_decisions(value)
    return normalized


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--decisions-json", type=Path)
    args = parser.parse_args(argv)

    try:
        generated = generate_outputs(
            args.inventory_json,
            args.output_dir,
            args.decisions_json,
        )
    except (OSError, InventoryGenerationError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    print(
        json.dumps(
            {
                "branches": len(_inventory_records(generated)),
                "risk_counts": generated["risk_counts"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _convert_branch(
    branch: Mapping[str, object],
    decision: Mapping[str, object] | None,
    position: int,
) -> Record:
    branch_id = _required_text(branch, "branch_id", position)
    source_risk = _required_text(branch, "risk_level", position)
    if source_risk not in RISK_LEVELS:
        raise InventoryGenerationError(f"record {position} has invalid risk_level: {source_risk}")
    if source_risk == "medium" and decision is None:
        raise InventoryGenerationError(f"Medium branch {branch_id} requires an explicit decision")
    if decision is not None and source_risk == "medium":
        _require_medium_decision(decision, branch_id)

    source_evidence = _evidence(branch.get("closure_evidence"), "closure_evidence", position)
    if source_risk == "medium":
        if decision is None:
            raise InventoryGenerationError(
                f"Medium branch {branch_id} requires an explicit decision"
            )
        materiality = _decision_text(
            _first_present(decision, ("materiality",)), "materiality", branch_id
        )
        closure_status = _decision_text(
            _first_present(decision, ("closure_status",)), "closure_status", branch_id
        )
    else:
        materiality = _default_materiality(source_risk)
        closure_status = _default_closure_status(source_risk)
    function = branch.get("function")
    if not isinstance(function, str) or not function.strip():
        function = "<module>"
    source_line = _required_positive_int(branch, "source_line", position)
    target_line = branch.get("target_line", source_line + 1)
    if not isinstance(target_line, int) or isinstance(target_line, bool) or target_line == 0:
        raise InventoryGenerationError(
            f"source record {position} field target_line must be a non-zero integer"
        )
    condition = branch.get("condition", branch.get("behavioral_requirement"))
    if not isinstance(condition, str) or not condition.strip():
        raise InventoryGenerationError(
            f"source record {position} field condition must be non-empty text"
        )
    record: Record = {
        "branch_id": branch_id,
        "file": _required_text(branch, "file", position),
        "function": function,
        "source_line": source_line,
        "target_line": target_line,
        "condition": condition,
        "branch_target": _required_text(branch, "target", position),
        "category": _required_text(branch, "risk_category", position),
        "risk_reason": _required_text(branch, "classification_basis", position),
        "materiality": materiality,
        "existing_evidence": source_evidence,
        "closure_requirement": _required_text(branch, "behavioral_requirement", position),
        "closure_status": closure_status,
        "risk_level": source_risk,
    }
    if decision is not None:
        record = _apply_decision(record, decision, branch_id, position)
    if record["risk_level"] == "medium":
        if decision is None:
            raise InventoryGenerationError(
                f"Medium branch {branch_id} requires an explicit decision"
            )
        _require_medium_decision(decision, branch_id)
    if record["closure_status"] == FORBIDDEN_CLOSURE_STATUS:
        raise InventoryGenerationError(
            f"branch {branch_id} cannot use {FORBIDDEN_CLOSURE_STATUS} in Phase 7.3"
        )
    return record


def _apply_decision(
    record: Record,
    decision: Mapping[str, object],
    branch_id: str,
    position: int,
) -> Record:
    result = dict(record)
    aliases = {
        "category": ("category",),
        "closure_requirement": ("closure_requirement", "requirement"),
        "closure_status": ("closure_status",),
        "materiality": ("materiality",),
        "risk_level": ("risk_level",),
        "risk_reason": ("risk_reason", "reason", "decision_reason"),
    }
    for output_field, candidate_fields in aliases.items():
        if not _contains_any(decision, candidate_fields):
            continue
        candidate = _first_present(decision, candidate_fields)
        result[output_field] = _decision_text(candidate, output_field, branch_id)
    if _contains_any(decision, ("existing_evidence", "evidence", "closure_evidence")):
        evidence = _first_present(decision, ("existing_evidence", "evidence", "closure_evidence"))
        result["existing_evidence"] = _evidence(evidence, "existing_evidence", position)
    return result


def _require_medium_decision(decision: Mapping[str, object], branch_id: str) -> None:
    if (
        _first_present(decision, ("materiality",)) is None
        or _first_present(decision, ("closure_status",)) is None
    ):
        raise InventoryGenerationError(
            f"Medium branch {branch_id} requires an explicit decision with materiality "
            "and closure_status"
        )


def _default_materiality(risk_level: str) -> str:
    if risk_level == "high":
        return "MATERIAL_PROMOTION_RELEVANT"
    if risk_level == "low":
        return "NON_MATERIAL_DEFENSIVE"
    raise InventoryGenerationError(
        "Medium branches cannot use heuristic materiality; provide a decision"
    )


def _default_closure_status(risk_level: str) -> str:
    if risk_level == "high":
        return "OPEN_PROMOTION_BLOCKER"
    if risk_level == "low":
        return "ACCEPTED_NON_MATERIAL"
    raise InventoryGenerationError(
        "Medium branches cannot use heuristic closure status; provide a decision"
    )


def _normalize_decisions(value: object | None) -> DecisionMap:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        wrapped = value.get("decisions")
        if wrapped is not None:
            return _normalize_decision_entries(wrapped)
        return _normalize_keyed_decisions(value)
    if _is_sequence(value):
        return _normalize_decision_entries(value)
    raise InventoryGenerationError("decisions JSON must be an object or a list")


def _normalize_keyed_decisions(value: Mapping[object, object]) -> DecisionMap:
    normalized: dict[str, Mapping[str, object]] = {}
    for raw_branch_id, raw_decision in value.items():
        if not isinstance(raw_branch_id, str) or not raw_branch_id.strip():
            raise InventoryGenerationError("decision branch_id keys must be non-empty text")
        if not isinstance(raw_decision, Mapping):
            raise InventoryGenerationError(f"decision for {raw_branch_id} must be an object")
        decision = dict(cast(Mapping[str, object], raw_decision))
        embedded_id = decision.get("branch_id")
        if embedded_id is not None and embedded_id != raw_branch_id:
            raise InventoryGenerationError(
                f"decision branch_id does not match its key: {raw_branch_id}"
            )
        decision.pop("branch_id", None)
        normalized[raw_branch_id] = decision
    return normalized


def _normalize_decision_entries(value: object) -> DecisionMap:
    if isinstance(value, Mapping):
        return _normalize_keyed_decisions(value)
    if not _is_sequence(value):
        raise InventoryGenerationError("decisions must be an object or a list")

    normalized: dict[str, Mapping[str, object]] = {}
    for position, raw_decision in enumerate(value):
        if not isinstance(raw_decision, Mapping):
            raise InventoryGenerationError(f"decision {position} must be an object")
        branch_id = raw_decision.get("branch_id")
        if not isinstance(branch_id, str) or not branch_id.strip():
            raise InventoryGenerationError(
                f"decision {position} must contain a non-empty branch_id"
            )
        if branch_id in normalized:
            raise InventoryGenerationError(f"duplicate decision branch_id: {branch_id}")
        decision = dict(cast(Mapping[str, object], raw_decision))
        decision.pop("branch_id", None)
        normalized[branch_id] = decision
    return normalized


def _source_branches(source_inventory: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = source_inventory.get("branches")
    if not _is_sequence(value):
        raise InventoryGenerationError("Phase 7.2 inventory branches must be a list")
    branches: list[Mapping[str, object]] = []
    for position, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise InventoryGenerationError(f"source branch {position} must be an object")
        branches.append(item)
    return branches


def _validate_source_phase(source_inventory: Mapping[str, object]) -> None:
    phase = source_inventory.get("phase", "PHASE7.2")
    if phase != "PHASE7.2":
        raise InventoryGenerationError(f"expected a PHASE7.2 inventory, got {phase!r}")


def _inventory_records(inventory: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = inventory.get("branches")
    if not _is_sequence(value):
        raise InventoryGenerationError("generated inventory branches must be a list")
    records: list[Mapping[str, object]] = []
    for position, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise InventoryGenerationError(f"generated record {position} must be an object")
        records.append(item)
    return records


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InventoryGenerationError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InventoryGenerationError(f"invalid JSON in {path}: {exc}") from exc


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _required_text(record: Mapping[str, object], field: str, position: int) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InventoryGenerationError(
            f"source record {position} field {field} must be non-empty text"
        )
    return value


def _required_positive_int(record: Mapping[str, object], field: str, position: int) -> int:
    value = record.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InventoryGenerationError(
            f"source record {position} field {field} must be a positive integer"
        )
    return value


def _decision_text(value: object, field: str, branch_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InventoryGenerationError(
            f"decision for {branch_id} field {field} must be non-empty text"
        )
    return value


def _evidence(value: object, field: str, position: int) -> list[str]:
    if isinstance(value, str):
        evidence: list[object] = [value]
    elif _is_sequence(value):
        evidence = list(value)
    else:
        raise InventoryGenerationError(
            f"record {position} field {field} must be text or a non-empty sequence"
        )
    if not evidence or any(not isinstance(item, str) or not item.strip() for item in evidence):
        raise InventoryGenerationError(
            f"record {position} field {field} must contain non-empty text"
        )
    return [cast(str, item) for item in evidence]


def _first_present(mapping: Mapping[str, object], fields: Sequence[str]) -> object | None:
    for field in fields:
        if field in mapping:
            return mapping[field]
    return None


def _contains_any(mapping: Mapping[str, object], fields: Sequence[str]) -> bool:
    return any(field in mapping for field in fields)


def _is_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _risk_counts(counts: Mapping[str, int]) -> dict[str, int]:
    return {risk_level: counts[risk_level] for risk_level in ("high", "medium", "low")}


def _markdown_cell(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
