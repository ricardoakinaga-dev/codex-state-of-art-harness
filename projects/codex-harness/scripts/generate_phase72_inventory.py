#!/usr/bin/env python3
"""Generate the Phase 7.2 residual-branch inventory from current coverage JSON.

This is evidence tooling only. It never excludes a branch and starts every
residual branch in the conservative deferred state. Closure is written only by
the Phase 7.2 integrator after targeted behavioral evidence exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

VALID_CLOSURE_STATES = frozenset(
    {
        "TESTED_PASS",
        "TESTED_FAIL_FIXED",
        "UNREACHABLE_PROVEN",
        "DEAD_CODE_REMOVED",
        "BLOCKED_ENVIRONMENT",
        "DEFERRED_BLOCKING_PROMOTION",
        "NOT_HIGH_RISK_RECLASSIFIED_WITH_EVIDENCE",
    }
)

_CRITICAL_PATTERN = re.compile(
    r"transaction|rollback|commit|atomic|sqlite|database|constraint|foreign.?key|"
    r"unique|idempot|concurr|migration|schema|checksum",
    re.IGNORECASE,
)
_HIGH_PATTERN = re.compile(
    r"authorization|auth|credential|secret|symlink|path|network|mcp|provider|shell|"
    r"retry|timeout|deadline|cancel|lock|dependency|unavailable|stale|digest|"
    r"fingerprint|artifact|manifest|evidence|partial|scope|progress|oscillat|attempt|"
    r"failure|stop",
    re.IGNORECASE,
)

_CATEGORY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("LEDGER_LOCKING", re.compile(r"ledger|lock|replay", re.IGNORECASE)),
    ("HOST_AUTH", re.compile(r"host|appserver|subprocess|transport", re.IGNORECASE)),
    ("AUTHORIZATION", re.compile(r"authorization|auth|credential|permission", re.IGNORECASE)),
    ("FILESYSTEM", re.compile(r"filesystem|path|symlink|directory|file|root", re.IGNORECASE)),
    ("PERSISTENCE", re.compile(r"persist|store|record|write|replace|fsync", re.IGNORECASE)),
    ("TRANSACTION", re.compile(r"transaction|commit|constraint|sqlite|database", re.IGNORECASE)),
    ("ROLLBACK", re.compile(r"rollback|recover", re.IGNORECASE)),
    ("CONCURRENCY", re.compile(r"concurr|race|version|double", re.IGNORECASE)),
    ("IDEMPOTENCY", re.compile(r"idempot|duplicate|replay", re.IGNORECASE)),
    ("MIGRATION", re.compile(r"migration|schema|checksum", re.IGNORECASE)),
    ("CANCELLATION", re.compile(r"cancel|interrupt", re.IGNORECASE)),
    ("PARTIAL_EXECUTION", re.compile(r"partial|incomplete", re.IGNORECASE)),
    ("TIMEOUT", re.compile(r"timeout|deadline", re.IGNORECASE)),
    ("RETRY", re.compile(r"retry|attempt|backoff", re.IGNORECASE)),
    (
        "FAILURE_ROUTING",
        re.compile(r"route|fallback|blocked|failure|stop|dependency", re.IGNORECASE),
    ),
    ("EVIDENCE_STALENESS", re.compile(r"stale|fresh|supersed|timestamp", re.IGNORECASE)),
    ("ARTIFACT_INTEGRITY", re.compile(r"artifact|digest|manifest|fingerprint", re.IGNORECASE)),
    ("RECOVERY", re.compile(r"recover|restore|interrupted", re.IGNORECASE)),
    ("STATE_TRANSITION", re.compile(r"state|status|lifecycle|transition", re.IGNORECASE)),
    ("SECURITY_BOUNDARY", re.compile(r"security|secret|credential|unsafe", re.IGNORECASE)),
    ("SCOPE_CONTROL", re.compile(r"scope|allowed|forbidden|policy", re.IGNORECASE)),
    ("NO_PROGRESS", re.compile(r"progress|stuck|budget", re.IGNORECASE)),
    ("OSCILLATION", re.compile(r"oscillat|cycle|repeat", re.IGNORECASE)),
    ("DEPENDENCY_FAILURE", re.compile(r"dependency|provider|unavailable|transport", re.IGNORECASE)),
    ("TELEMETRY_INTEGRITY", re.compile(r"telemetry|event|correlation|redact", re.IGNORECASE)),
)


def _branch_id(path: str, source: int, target: int) -> str:
    value = f"{path}:{source}->{target}".encode()
    return "P7.2-BRANCH-" + hashlib.sha256(value).hexdigest()[:16]


def _line(lines: list[str], number: int) -> str:
    return lines[number - 1].strip() if 1 <= number <= len(lines) else "<exit>"


def _function_for(functions: dict[str, Any], line: int) -> str:
    candidates = [
        (int(details.get("start_line", 0)), name)
        for name, details in functions.items()
        if int(details.get("start_line", 0)) <= line
    ]
    return max(candidates)[1] if candidates else "<module>"


def _category(path: str, function: str, condition: str, *, risk: str) -> str:
    context = " ".join((path, function, condition))
    for category, pattern in _CATEGORY_RULES:
        if pattern.search(context):
            return category
    return "OTHER_HIGH_RISK" if risk == "high" else "OTHER"


def _risk(path: str, function: str, condition: str) -> tuple[str, str]:
    context = " ".join((path, function, condition))
    if _CRITICAL_PATTERN.search(context):
        return "high", "material integrity vocabulary requires behavioral closure"
    if _HIGH_PATTERN.search(context):
        return "high", "material failure-boundary vocabulary requires behavioral closure"
    if re.search(r"assert|raise|invalid|parse|schema|enum|type|none|empty|missing", context, re.I):
        return "medium", "validation/defensive branch requires qualitative review"
    return "low", "residual defensive branch requires qualitative review before exclusion"


def _requirement(category: str, condition: str) -> str:
    if category in {"LEDGER_LOCKING", "CONCURRENCY", "IDEMPOTENCY"}:
        return (
            "Reject unsafe duplicate/contended state and preserve ownership "
            "and persisted invariants."
        )
    if category in {"HOST_AUTH", "AUTHORIZATION", "SECURITY_BOUNDARY"}:
        return "Fail closed when identity, authority, scope or binding is absent, invalid or stale."
    if category in {"FILESYSTEM", "SCOPE_CONTROL"}:
        return "Reject escape, symlink, traversal or unauthorized path use without side effects."
    if category in {"PERSISTENCE", "TRANSACTION", "ROLLBACK", "MIGRATION"}:
        return "Preserve atomic, identity-bound, recoverable state and never expose false success."
    if category in {"CANCELLATION", "PARTIAL_EXECUTION", "TIMEOUT", "RETRY"}:
        return (
            "Expose the truthful terminal outcome and bound material execution "
            "and retry side effects."
        )
    if category in {"EVIDENCE_STALENESS", "ARTIFACT_INTEGRITY", "RECOVERY"}:
        return (
            "Reject stale, corrupt, superseded or mismatched evidence rather "
            "than inventing success."
        )
    if category in {"TELEMETRY_INTEGRITY", "NO_PROGRESS", "OSCILLATION"}:
        return (
            "Emit truthful bounded telemetry and stop when progress or "
            "correlation cannot be proven."
        )
    if category == "FAILURE_ROUTING":
        return (
            "Route failure explicitly with reason, blocker, selected/omitted "
            "alternatives and unknowns."
        )
    return f"Safely handle residual condition: {condition}"


def build_inventory(root: Path, coverage_path: Path) -> dict[str, Any]:
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    branches: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for source_path, details in sorted(coverage["files"].items()):
        source_file = root / source_path
        lines = (
            source_file.read_text(encoding="utf-8").splitlines() if source_file.is_file() else []
        )
        file_ids: list[str] = []
        for source_line, target_line in details.get("missing_branches", []):
            function = _function_for(details.get("functions", {}), source_line)
            condition = _line(lines, source_line)
            target = _line(lines, target_line)
            risk, basis = _risk(source_path, function, condition)
            category = _category(source_path, function, condition, risk=risk)
            branch_id = _branch_id(source_path, source_line, target_line)
            file_ids.append(branch_id)
            tests: list[str] = []
            source_name = Path(source_path).stem
            for candidate in (
                root / "tests" / "unit" / f"test_{source_name}.py",
                root / "tests" / "integration" / f"test_{source_name}.py",
                root / "pilots/backend-appointment-api/tests/test_pilot.py",
            ):
                if candidate.is_file() and candidate.relative_to(root).as_posix() not in tests:
                    tests.append(candidate.relative_to(root).as_posix())
            branches.append(
                {
                    "branch_id": branch_id,
                    "legacy_branch_id": "P7.1-BRANCH-"
                    + hashlib.sha256(
                        f"{source_path}:{source_line}->{target_line}".encode()
                    ).hexdigest()[:12],
                    "file": source_path,
                    "function": function,
                    "source_line": source_line,
                    "target_line": target_line,
                    "condition": condition,
                    "target": target,
                    "risk_category": category,
                    "risk_level": risk,
                    "classification_basis": basis,
                    "current_test": tests,
                    "behavioral_requirement": _requirement(category, condition),
                    "closure_status": "DEFERRED_BLOCKING_PROMOTION",
                    "closure_evidence": (
                        "Initial conservative inventory; targeted evidence pending."
                    ),
                }
            )
        files.append(
            {
                "path": source_path,
                "summary": details.get("summary", {}),
                "missing_branch_ids": file_ids,
            }
        )
    risk_counts = Counter(item["risk_level"] for item in branches)
    category_counts = Counter(item["risk_category"] for item in branches)
    try:
        coverage_reference = coverage_path.relative_to(root).as_posix()
    except ValueError:
        coverage_reference = str(coverage_path)
    return {
        "schema_version": "P7.2-HIGH-RISK-BRANCH-INVENTORY-1",
        "phase": "PHASE7.2",
        "feature_freeze": "P7_2_FEATURE_FREEZE",
        "source_coverage_report": coverage_reference,
        "coverage_meta": coverage.get("meta", {}),
        "totals": coverage["totals"],
        "branches": sorted(branches, key=lambda item: item["branch_id"]),
        "files": files,
        "risk_counts": dict(sorted(risk_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "valid_closure_states": sorted(VALID_CLOSURE_STATES),
        "review_status": "INITIAL_CONSERVATIVE_INVENTORY",
        "exclusions": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--coverage-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inventory = build_inventory(args.project_root.resolve(), args.coverage_json.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "high-risk-branch-inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    totals = inventory["totals"]
    high = inventory["risk_counts"].get("high", 0)
    (args.output_dir / "high-risk-branch-inventory.md").write_text(
        "\n".join(
            (
                "# Phase 7.2 High-Risk Branch Inventory",
                "",
                (
                    "Generated from current branch-aware coverage with no branch "
                    "exclusions; coverage-reported excluded lines remain visible."
                ),
                "",
                f"- residual branches: `{totals['missing_branches']}`",
                f"- residual high-risk branches: `{high}`",
                f"- line coverage: `{totals['percent_statements_covered']}%`",
                f"- branch coverage: `{totals['percent_branches_covered']}%`",
                "- initial closure state: `DEFERRED_BLOCKING_PROMOTION` for every residual arc",
                "",
                "The JSON record is authoritative. Closure states may change only"
                " after the branch-to-test/proof evidence is current and independently reviewed.",
                "",
                "## Risk categories",
                "",
                *[
                    f"- `{category}`: `{count}`"
                    for category, count in sorted(inventory["category_counts"].items())
                ],
                "",
                (
                    "No branch is silently ignored, excluded, renamed away, or "
                    "downgraded by this generator."
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"branches": len(inventory["branches"]), "risk_counts": inventory["risk_counts"]},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
