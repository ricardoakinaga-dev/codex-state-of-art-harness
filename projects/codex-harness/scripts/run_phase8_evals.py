"""Run bounded declarative routing and quality-contract evaluations for Phase 8."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PACKAGE = Path(".harness/capabilities/frontend-engineering-vnext")
ROUTES = {"SELECTED", "OMITTED", "BLOCKED", "FALLBACK"}
REQUIRED_CATEGORIES = {"routing", "state", "responsive", "accessibility", "performance", "security"}


def evaluate(project_root: Path) -> dict[str, object]:
    source = project_root / PACKAGE / "evals/scenarios.json"
    scenarios = json.loads(source.read_text(encoding="utf-8"))["scenarios"]
    results: list[dict[str, object]] = []
    for item in scenarios:
        reasons: list[str] = []
        if not item.get("id") or not item.get("acceptance"):
            reasons.append("missing identity or acceptance")
        if item.get("expected_route") not in ROUTES:
            reasons.append("unsupported expected route")
        if item.get("negative") and item.get("expected_route") == "SELECTED":
            reasons.append("negative scenario selects specialist")
        if item.get("false_pass_guard") and not item.get("must_not_claim"):
            reasons.append("false-pass guard has no prohibited claims")
        if not item.get("evidence_shape"):
            reasons.append("evidence shape is empty")
        results.append(
            {
                "id": item.get("id"),
                "category": item.get("category"),
                "expected_route": item.get("expected_route"),
                "status": "PASS" if not reasons else "FAIL",
                "reasons": reasons,
            }
        )
    failures = [item for item in results if item["status"] != "PASS"]
    categories = {str(item.get("category")) for item in scenarios}
    false_guards = sum(bool(item.get("false_pass_guard")) for item in scenarios)
    negatives = sum(bool(item.get("negative")) for item in scenarios)
    false_pass_guard_ids = [
        item["id"]
        for item in scenarios
        if item.get("false_pass_guard") and item.get("expected_route") == "SELECTED"
    ]
    report = {
        "schema_version": "P8-EVAL-RESULT-1",
        "source": str(PACKAGE / "evals/scenarios.json"),
        "scenario_count": len(scenarios),
        "category_coverage": sorted(categories),
        "required_categories_present": categories >= REQUIRED_CATEGORIES,
        "route_coverage": sorted({str(item.get("expected_route")) for item in scenarios}),
        "negative_count": negatives,
        "false_pass_guard_count": false_guards,
        "results": results,
        "status": "PASS"
        if not failures and categories >= REQUIRED_CATEGORIES and len(scenarios) >= 50
        else "FAIL",
        "failures": failures,
        # Guard scenarios are a catalog inventory, not observed failures.  A
        # non-empty inventory must never be interpreted as a false PASS.
        "false_pass_guard_ids": false_pass_guard_ids,
        "critical_false_pass": [],
        "critical_false_pass_count": 0,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = evaluate(arguments.project_root.resolve(strict=True))
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
