"""Canonical, machine-readable risk semantics for Phase 7.3 evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

RISK_LEVELS = frozenset({"high", "medium", "low"})
MATERIALITIES = frozenset(
    {
        "MATERIAL_PROMOTION_RELEVANT",
        "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE",
        "NON_MATERIAL_DEFENSIVE",
        "UNREACHABLE_BY_CONTRACT",
        "DEAD_CODE",
        "ENVIRONMENT_DEPENDENT",
        "PLATFORM_SPECIFIC",
        "DOCUMENTATION_ONLY / DIAGNOSTIC_ONLY",
    }
)
CLOSURE_STATES = frozenset(
    {
        "TESTED_PASS",
        "TESTED_FAIL_FIXED",
        "UNREACHABLE_PROVEN",
        "DEAD_CODE_REMOVED",
        "ACCEPTED_NON_MATERIAL",
        "BLOCKED_ENVIRONMENT_NON_PROMOTION_BLOCKING",
        "BLOCKED_ENVIRONMENT_PROMOTION_BLOCKING",
        "OPEN_PROMOTION_BLOCKER",
    }
)

CLOSED_STATES = frozenset(
    {
        "TESTED_PASS",
        "TESTED_FAIL_FIXED",
        "UNREACHABLE_PROVEN",
        "DEAD_CODE_REMOVED",
        "ACCEPTED_NON_MATERIAL",
        "BLOCKED_ENVIRONMENT_NON_PROMOTION_BLOCKING",
    }
)
BLOCKED_STATES = frozenset(
    {
        "BLOCKED_ENVIRONMENT_NON_PROMOTION_BLOCKING",
        "BLOCKED_ENVIRONMENT_PROMOTION_BLOCKING",
    }
)
OPEN_ACTIONABLE_STATES = frozenset(
    {"BLOCKED_ENVIRONMENT_PROMOTION_BLOCKING", "OPEN_PROMOTION_BLOCKER"}
)
PROMOTION_RELEVANT_MATERIALITIES = frozenset(
    {
        "MATERIAL_PROMOTION_RELEVANT",
        "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE",
    }
)

REQUIRED_FIELDS = frozenset(
    {
        "branch_id",
        "file",
        "function",
        "source_line",
        "branch_target",
        "category",
        "risk_reason",
        "materiality",
        "existing_evidence",
        "closure_requirement",
        "closure_status",
        "risk_level",
    }
)
COUNT_KEYS = (
    "total",
    "high",
    "medium",
    "low",
    "classified_high",
    "classified_medium",
    "classified_low",
    "open_actionable_high",
    "open_actionable_medium",
    "promotion_blocking_high",
    "promotion_blocking_medium",
    "closed_high",
    "closed_medium",
    "material_medium",
    "accepted_residual_medium",
    "blocked_medium",
)


class RiskSemanticError(ValueError):
    """Raised when a Phase 7.3 risk record or count surface is ambiguous."""


def validate_inventory_records(records: Sequence[Mapping[str, object]]) -> None:
    """Validate the explicit schema and semantic values for every risk record."""

    branch_ids: set[str] = set()
    for position, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise RiskSemanticError(f"record {position} must be an object")

        missing = sorted(REQUIRED_FIELDS - record.keys())
        if missing:
            raise RiskSemanticError(
                f"record {position} is missing required fields: {', '.join(missing)}"
            )

        branch_id = _text(record, "branch_id", position)
        if branch_id in branch_ids:
            raise RiskSemanticError(f"branch_id must be unique: {branch_id}")
        branch_ids.add(branch_id)

        risk_level = _text(record, "risk_level", position)
        if risk_level not in RISK_LEVELS:
            raise RiskSemanticError(f"record {position} has invalid risk_level: {risk_level}")

        materiality = _text(record, "materiality", position)
        if materiality not in MATERIALITIES:
            raise RiskSemanticError(f"record {position} has invalid materiality: {materiality}")

        closure_status = _text(record, "closure_status", position)
        if closure_status not in CLOSURE_STATES:
            raise RiskSemanticError(
                f"record {position} has invalid closure_status: {closure_status}"
            )

        _positive_int(record, "source_line", position)
        for field in ("file", "function", "branch_target", "category", "risk_reason"):
            _text(record, field, position)
        _text(record, "closure_requirement", position)
        _evidence(record, position)

        if (
            closure_status == "ACCEPTED_NON_MATERIAL"
            and materiality in PROMOTION_RELEVANT_MATERIALITIES
        ):
            raise RiskSemanticError(
                f"record {position} cannot accept promotion-relevant materiality as non-material"
            )


def semantic_counts(records: Sequence[Mapping[str, object]]) -> dict[str, int]:
    """Return all promotion-relevant counts from one validated inventory."""

    validate_inventory_records(records)
    counts = {key: 0 for key in COUNT_KEYS}
    counts["total"] = len(records)

    for record in records:
        risk_level = _text(record, "risk_level", 0)
        closure_status = _text(record, "closure_status", 0)
        materiality = _text(record, "materiality", 0)
        counts[risk_level] += 1
        counts[f"classified_{risk_level}"] += 1
        if closure_status in OPEN_ACTIONABLE_STATES:
            counts[f"open_actionable_{risk_level}"] += 1
        if closure_status in OPEN_ACTIONABLE_STATES:
            counts[f"promotion_blocking_{risk_level}"] += 1
        if closure_status in CLOSED_STATES:
            closed_key = f"closed_{risk_level}"
            if closed_key in counts:
                counts[closed_key] += 1
        if risk_level == "medium":
            if materiality in PROMOTION_RELEVANT_MATERIALITIES:
                counts["material_medium"] += 1
            if closure_status == "ACCEPTED_NON_MATERIAL":
                counts["accepted_residual_medium"] += 1
            if closure_status in BLOCKED_STATES:
                counts["blocked_medium"] += 1

    return counts


def validate_count_consistency(**surfaces: Mapping[str, int]) -> None:
    """Require every published promotion surface to expose identical counts."""

    if not surfaces:
        raise RiskSemanticError("at least one count surface is required")

    normalized: dict[str, dict[str, int]] = {}
    for name, surface in surfaces.items():
        missing = [key for key in COUNT_KEYS if key not in surface]
        if missing:
            raise RiskSemanticError(f"{name} count surface is missing: {', '.join(missing)}")
        invalid = [key for key in COUNT_KEYS if not _is_non_negative_int(surface[key])]
        if invalid:
            raise RiskSemanticError(
                f"{name} count surface has invalid values: {', '.join(invalid)}"
            )
        normalized[name] = {key: surface[key] for key in COUNT_KEYS}

    names = tuple(normalized)
    expected = normalized[names[0]]
    for name in names[1:]:
        if normalized[name] != expected:
            differences = [key for key in COUNT_KEYS if normalized[name][key] != expected[key]]
            raise RiskSemanticError(
                f"count surface {name} disagrees with {names[0]}: {', '.join(differences)}"
            )


def promotion_gate_is_open(counts: Mapping[str, int]) -> bool:
    """Return whether any actionable High or Medium risk blocks promotion."""

    validate_count_consistency(inventory=counts)
    return any(
        counts[key] > 0
        for key in (
            "open_actionable_high",
            "open_actionable_medium",
            "promotion_blocking_high",
            "promotion_blocking_medium",
        )
    )


def _text(record: Mapping[str, object], field: str, position: int) -> str:
    value = record[field]
    if not isinstance(value, str) or not value.strip():
        raise RiskSemanticError(f"record {position} field {field} must be non-empty text")
    return value


def _positive_int(record: Mapping[str, object], field: str, position: int) -> None:
    value = record[field]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RiskSemanticError(f"record {position} field {field} must be a positive integer")


def _evidence(record: Mapping[str, object], position: int) -> None:
    value = record["existing_evidence"]
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise RiskSemanticError(
            f"record {position} field existing_evidence must be a non-empty sequence"
        )
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise RiskSemanticError(
            f"record {position} field existing_evidence must contain non-empty text"
        )


def _is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
