#!/usr/bin/env python3
"""Generate auditable Phase 7.2 branch traceability and category reports."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

REQUIRED_CATEGORIES = (
    "LEDGER_LOCKING",
    "HOST_AUTH",
    "AUTHORIZATION",
    "FILESYSTEM",
    "PERSISTENCE",
    "TRANSACTION",
    "ROLLBACK",
    "CONCURRENCY",
    "IDEMPOTENCY",
    "MIGRATION",
    "CANCELLATION",
    "PARTIAL_EXECUTION",
    "TIMEOUT",
    "RETRY",
    "FAILURE_ROUTING",
    "EVIDENCE_STALENESS",
    "ARTIFACT_INTEGRITY",
    "RECOVERY",
    "STATE_TRANSITION",
    "SECURITY_BOUNDARY",
    "SCOPE_CONTROL",
    "NO_PROGRESS",
    "OSCILLATION",
    "DEPENDENCY_FAILURE",
    "TELEMETRY_INTEGRITY",
    "OTHER_HIGH_RISK",
)

SOURCE_TARGETS = {
    "phase3_paths.py": {"P72-T06", "P72-T07", "P72-T08", "P72-T22", "P72-T29", "P72-R03"},
    "phase4_host.py": {
        "P72-T01",
        "P72-T02",
        "P72-T03",
        "P72-T04",
        "P72-T05",
        "P72-T14",
        "P72-T16",
        "P72-T17",
        "P72-R04",
        "P72-R06",
    },
    "boundary.py": {"P72-T09", "P72-T23", "P72-T24", "P72-T27", "P72-R01"},
    "persistence.py": {"P72-T10", "P72-T24", "P72-T27", "P72-R01"},
    "phase4_artifacts.py": {"P72-T18", "P72-T33"},
    "phase4_cli.py": {"P72-T19", "P72-T33"},
    "phase4_execution.py": {
        "P72-T11",
        "P72-T12",
        "P72-T20",
        "P72-T30",
        "P72-R02",
        "P72-R06",
    },
    "execution.py": {"P72-T13", "P72-R02", "P72-R07", "P72-R09"},
    "phase5_cli.py": {"P72-T19", "P72-T31", "P72-T32", "P72-T33"},
    "phase5_policy.py": {"P72-T19", "P72-T33"},
    "phase6_stop.py": {"P72-T34"},
    "providers.py": {"P72-T15", "P72-R08", "P72-R09"},
    "phase7_backend.py": {"P72-T18", "P72-T25"},
    "phase7_host.py": {"P72-R05", "P72-R07"},
}


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _slug(value: str) -> str:
    return value.lower().replace("_", "-")


def _tests_for_branch(
    branch: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    source_name = Path(str(branch["file"])).name
    selected_ids = set(SOURCE_TARGETS.get(source_name, ()))
    candidates = set(branch.get("current_test", ()))
    selected = [
        item
        for item in catalog.values()
        if item["id"] in selected_ids or item.get("path") in candidates
    ]
    unique: dict[str, dict[str, Any]] = {item["id"]: item for item in selected}
    strength = "BEHAVIORAL_TARGETED_OR_REGRESSION" if unique else "NO_DIRECT_TEST_MAPPING"
    return [
        {
            "test_id": item["id"],
            "path": item["path"],
            "nodeid": item.get("nodeid"),
            "result": item["result"],
            "relation": "behavioral evidence is relevant; coverage still reports this arc residual",
        }
        for item in sorted(unique.values(), key=lambda value: value["id"])
    ], strength


def build_traceability(
    inventory: dict[str, Any], catalog: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for branch in inventory["branches"]:
        tests, strength = _tests_for_branch(branch, catalog)
        records.append(
            {
                "branch_id": branch["branch_id"],
                "legacy_branch_id": branch["legacy_branch_id"],
                "location": {
                    "file": branch["file"],
                    "function": branch["function"],
                    "source_line": branch["source_line"],
                    "target_line": branch["target_line"],
                    "condition": branch["condition"],
                    "target": branch["target"],
                },
                "risk_level": branch["risk_level"],
                "risk_category": branch["risk_category"],
                "behavioral_invariant": branch["behavioral_requirement"],
                "tests": tests,
                "test_result": "PASS"
                if tests and all(item["result"] == "PASS" for item in tests)
                else "NO_DIRECT_RESULT",
                "coverage_result": "RESIDUAL_BRANCH_NOT_DIRECTLY_COVERED",
                "mapping_strength": strength,
                "closure_status": branch["closure_status"],
                "closure_evidence": branch["closure_evidence"],
                "promotion_effect": (
                    "BLOCKING"
                    if branch["risk_level"] == "high"
                    and branch["closure_status"] == "DEFERRED_BLOCKING_PROMOTION"
                    else "CLOSED_WITH_PROOF"
                    if branch["risk_level"] == "high"
                    else "QUALITATIVE_REVIEW_REQUIRED"
                ),
            }
        )
    status_counts = Counter(item["closure_status"] for item in records)
    strength_counts = Counter(item["mapping_strength"] for item in records)
    risk_counts = Counter(item["risk_level"] for item in records)
    category_counts = Counter(item["risk_category"] for item in records)
    return {
        "schema_version": "P7.2-BRANCH-TEST-TRACEABILITY-1",
        "phase": "PHASE7.2",
        "feature_freeze": "P7_2_FEATURE_FREEZE",
        "generated_at": datetime.now().astimezone().isoformat(),
        "inventory": "evidence/phase-7.2/high-risk-branch-inventory.json",
        "test_catalog": "evidence/phase-7.2/test-catalog.json",
        "coverage_artifact": "evidence/phase-7.2/coverage-final.json",
        "records": records,
        "summary": {
            "total_residual_branches": len(records),
            "risk_counts": dict(sorted(risk_counts.items())),
            "category_counts": dict(sorted(category_counts.items())),
            "closure_status_counts": dict(sorted(status_counts.items())),
            "mapping_strength_counts": dict(sorted(strength_counts.items())),
            "high_risk_unresolved": sum(
                1
                for item in records
                if item["risk_level"] == "high"
                and item["closure_status"] == "DEFERRED_BLOCKING_PROMOTION"
            ),
        },
        "interpretation": {
            "test_result": "The referenced test or regression suite passed.",
            "coverage_result": (
                "The exact source-to-target arc remains absent from the fresh "
                "branch-aware coverage result."
            ),
            "closure_policy": (
                "A passing neighboring behavior does not close a residual arc; "
                "closure remains deferred until direct execution or a separately "
                "reviewable proof exists."
            ),
        },
    }


def write_category_reports(traceability: dict[str, Any], output_dir: Path) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in traceability["records"]:
        grouped[record["risk_category"]].append(record)
    category_names = sorted(set(REQUIRED_CATEGORIES) | set(grouped))
    reports: dict[str, Any] = {}
    for category in category_names:
        records = grouped.get(category, [])
        closure_counts = Counter(item["closure_status"] for item in records)
        risk_counts = Counter(item["risk_level"] for item in records)
        unresolved = [
            item["branch_id"]
            for item in records
            if item["closure_status"] == "DEFERRED_BLOCKING_PROMOTION"
        ]
        reports[category] = {
            "category": category,
            "branch_count": len(records),
            "risk_counts": dict(sorted(risk_counts.items())),
            "closure_status_counts": dict(sorted(closure_counts.items())),
            "unresolved_branch_ids": unresolved,
            "result": "BLOCKED_BY_RESIDUAL_ARCS" if unresolved else "CLOSED",
            "evidence_policy": (
                "See branch-test-traceability.json for every branch record and test relation."
            ),
        }
        lines = [
            f"# Phase 7.2 Category: {category}",
            "",
            f"- residual branches: `{len(records)}`",
            f"- high-risk branches: `{sum(1 for item in records if item['risk_level'] == 'high')}`",
            f"- unresolved/deferred branches: `{len(unresolved)}`",
            f"- result: `{reports[category]['result']}`",
            "",
            (
                "A neighboring test result is not treated as direct branch closure. "
                "The exact branch records and current coverage relation are "
                "authoritative in `branch-test-traceability.json`."
            ),
            "",
        ]
        if unresolved:
            lines.extend(
                (
                    "## Deferred branch IDs",
                    "",
                    *[f"- `{branch_id}`" for branch_id in unresolved],
                    "",
                )
            )
        else:
            lines.extend(("No residual branch in this category remains deferred.", ""))
        (output_dir / f"category-{_slug(category)}.md").write_text(
            "\n".join(lines), encoding="utf-8"
        )
    (output_dir / "category-reports.json").write_text(
        json.dumps(
            {
                "schema_version": "P7.2-CATEGORY-REPORTS-1",
                "phase": "PHASE7.2",
                "feature_freeze": "P7_2_FEATURE_FREEZE",
                "reports": reports,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--test-catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inventory = _load_object(args.inventory)
    raw_catalog = _load_object(args.test_catalog)
    catalog = {item["id"]: item for item in raw_catalog["tests"]}
    if len(catalog) != len(raw_catalog["tests"]):
        raise ValueError("test catalog IDs must be unique")
    traceability = build_traceability(inventory, catalog)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "branch-test-traceability.json").write_text(
        json.dumps(traceability, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    high = [
        item
        for item in traceability["records"]
        if item["risk_level"] == "high" and item["closure_status"] == "DEFERRED_BLOCKING_PROMOTION"
    ]
    deferred_count = sum(
        1
        for item in traceability["records"]
        if item["closure_status"] == "DEFERRED_BLOCKING_PROMOTION"
    )
    lines = [
        "# Phase 7.2 Branch-to-Test Traceability",
        "",
        (
            "The JSON file is authoritative. Every current residual arc is listed; "
            "no residual is silently excluded."
        ),
        "",
        f"- residual branches: `{len(traceability['records'])}`",
        f"- high-risk residual branches: `{len(high)}`",
        (f"- exact arcs still deferred: `{deferred_count}`"),
        "- test result semantics: referenced tests passed when marked `PASS`",
        (
            "- coverage semantics: `RESIDUAL_BRANCH_NOT_DIRECTLY_COVERED` means "
            "the exact arc remains absent from fresh coverage"
        ),
        "",
        "## Closure policy",
        "",
        (
            "A regression or neighboring behavioral test is useful evidence, but it "
            "does not close an uncovered source-to-target arc by itself. Material "
            "branches therefore remain `DEFERRED_BLOCKING_PROMOTION` until direct "
            "execution or independently reviewable proof is recorded; recorded "
            "proof states are preserved explicitly."
        ),
        "",
        "## Category reports",
        "",
        *[
            f"- `category-{_slug(category)}.md`"
            for category in sorted(
                set(REQUIRED_CATEGORIES)
                | set(item["risk_category"] for item in traceability["records"])
            )
        ],
        "",
    ]
    (args.output_dir / "branch-test-traceability.md").write_text("\n".join(lines), encoding="utf-8")
    write_category_reports(traceability, args.output_dir)
    print(json.dumps(traceability["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
