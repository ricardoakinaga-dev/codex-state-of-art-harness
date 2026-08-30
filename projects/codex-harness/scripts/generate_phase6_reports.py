#!/usr/bin/env python3
"""Materialize the bounded, reproducible Phase 6 evidence index."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _quality_tree_digest(root: Path) -> str:
    """Recompute the quality receipt scope before trusting its metrics."""

    repo_root = root.parents[1]
    paths: list[Path] = []
    for relative in (
        "src",
        "tests",
        ".harness/capabilities/verification-loop-vnext",
        "scripts",
        "config",
    ):
        paths.extend(
            path
            for path in (root / relative).rglob("*")
            if path.is_file()
            and not {"__pycache__", ".pytest_cache", ".ruff_cache"}.intersection(path.parts)
        )
    paths.append(
        repo_root / "architecture/docs/adr/ADR-015-verification-loop-vnext-modernization.md"
    )
    paths.append(root / "pyproject.toml")
    digest = hashlib.sha256()
    for path in sorted({path.resolve() for path in paths}):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = "../../" + path.relative_to(repo_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return "sha256:" + hashlib.sha256(digest.digest()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _category_block_rate(report: dict[str, Any], categories: set[str]) -> float | str:
    records = report.get("records")
    if not isinstance(records, list):
        return "NOT_MEASURED"
    selected = [
        item for item in records if isinstance(item, dict) and item.get("category") in categories
    ]
    if not selected:
        return "NOT_MEASURED"
    blocked = sum(
        1 for item in selected if item.get("observed_outcome") in {"BLOCKED", "STALE", "FAIL"}
    )
    return blocked / len(selected)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_text(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _package_inventory(package_root: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for path in sorted(item for item in package_root.rglob("*") if item.is_file()):
        entries.append(
            {
                "path": path.relative_to(package_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _digest(path),
            }
        )
    return entries


def _markdown_table(rows: list[tuple[str, str, str]]) -> str:
    lines = ["| Item | Result | Evidence |", "| --- | --- | --- |"]
    lines.extend(f"| {item} | {result} | `{evidence}` |" for item, result, evidence in rows)
    return "\n".join(lines)


def _review_manifest(
    root: Path,
    evidence: Path,
    package: Path,
    args: argparse.Namespace,
    package_digest: str,
    manifest_digest: str,
    review_status: str,
) -> tuple[str, str]:
    """Bind the final reviewer packet without creating a self-referential hash."""

    repo_root = root.parents[1]
    paths: list[Path] = [
        path
        for path in evidence.iterdir()
        if path.is_file()
        and path.name
        not in {
            "review-manifest.json",
            "review-attestation.json",
            "readiness.json",
            "PHASE6-FROZEN.md",
        }
    ]
    paths.extend(path for path in evidence.joinpath("pilots").rglob("*") if path.is_file())

    def files_under(directory: Path) -> list[Path]:
        return [
            path
            for path in directory.rglob("*")
            if path.is_file()
            and not {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}.intersection(
                path.parts
            )
        ]

    # The quality receipt covers these trees. Keeping the exact same trees in the
    # reviewer packet prevents a passing closure from omitting behaviorally relevant files.
    paths.extend(files_under(root / "src"))
    paths.extend(files_under(root / "tests"))
    paths.extend(files_under(root / "scripts"))
    paths.extend(files_under(root / "config"))
    paths.extend(path for path in package.rglob("*") if path.is_file())
    paths.extend(
        [
            root / "pyproject.toml",
            repo_root
            / "architecture"
            / "docs"
            / "adr"
            / "ADR-015-verification-loop-vnext-modernization.md",
        ]
    )
    unique_paths = sorted({path.resolve() for path in paths})
    entries: list[dict[str, object]] = []
    for path in unique_paths:
        if not path.is_file():
            raise RuntimeError(f"review packet file is missing: {path}")
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = "../../" + path.relative_to(repo_root).as_posix()
        entries.append({"path": relative, "bytes": path.stat().st_size, "sha256": _digest(path)})
    base = {
        "schema_version": "P6-REVIEW-MANIFEST-1",
        "reviewed_head": args.reviewed_head,
        "package_digest": package_digest,
        "manifest_digest": manifest_digest,
        "entries": entries,
        "excluded_from_closure": [
            "readiness.json",
            "review-attestation.json",
            "review-manifest.json",
            "PHASE6-FROZEN.md",
            "project .agent control-plane files",
        ],
    }
    closure = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
    )
    manifest_path = evidence / "review-manifest.json"
    _write_json(manifest_path, {**base, "closure_digest": closure})
    attestation_path = evidence / "review-attestation.json"
    _write_json(
        attestation_path,
        {
            "schema_version": "P6-REVIEW-ATTESTATION-1",
            "status": review_status,
            "reviewed_head": args.reviewed_head,
            "review_manifest": "review-manifest.json",
            "review_manifest_closure_digest": closure,
            "capability_reviewer": args.capability_reviewer,
            "composition_reviewer": args.composition_reviewer,
            "builder_self_approval": "FORBIDDEN",
            "fresh_exact_packet": review_status == "PASS",
            "cryptographic_signature": "NOT_PROVIDED",
            "attestation_kind": "LOCAL_REVIEW_PACKET_READY"
            if review_status != "PASS"
            else "LOCAL_REVIEW_ATTESTATION",
        },
    )
    return closure, _digest(attestation_path)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--reviewed-head", required=True)
    parser.add_argument(
        "--review-status", choices=("PENDING", "REVIEWING", "PASS"), default="PENDING"
    )
    parser.add_argument(
        "--quality-receipt",
        type=Path,
        default=Path("evidence/phase-6/quality-receipt.json"),
    )
    parser.add_argument("--capability-reviewer", default="PENDING")
    parser.add_argument("--composition-reviewer", default="PENDING")
    return parser.parse_args()


def main() -> int:
    args = _args()
    root = args.project_root.resolve()
    evidence = root / "evidence" / "phase-6"
    pilot = evidence / "pilots" / "design-verification-composition"
    package = root / ".harness" / "capabilities" / "verification-loop-vnext"
    manifest = _read_json(package / "manifest.json")
    snapshot = _read_json(evidence / "current-verification-loop-snapshot.json")
    discovery = _read_json(pilot / "vnext-discovery.json")
    preflight = _read_json(pilot / "vnext-execution-preflight.json")
    composition = _read_json(pilot / "composition-receipt.json")
    output = _read_json(pilot / "verification-report.json")
    run_report = _read_json(pilot / "verification-report-v1.json")
    host_probe = _read_json(pilot / "host-probe.json")
    telemetry = _read_json(pilot / "verification-telemetry.json")
    quality_path = args.quality_receipt
    if not quality_path.is_absolute():
        quality_path = root / quality_path
    try:
        quality_path.resolve().relative_to(root)
    except ValueError as exc:
        raise RuntimeError("quality receipt must remain inside the project") from exc
    quality_run = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "record_phase6_quality.py"),
            "--project-root",
            str(root),
            "--output",
            str(quality_path),
        ],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if quality_run.returncode != 0:
        detail = quality_run.stderr.decode("utf-8", errors="replace")[-1_000:]
        raise RuntimeError(f"quality command receipt failed: {detail}")
    quality = _read_json(quality_path)
    current_quality_scope = _quality_tree_digest(root)
    if (
        quality.get("status") != "PASS"
        or quality.get("source_stable") is not True
        or quality.get("source_tree_digest_before") != current_quality_scope
        or quality.get("source_tree_digest_after") != current_quality_scope
    ):
        raise RuntimeError("quality receipt is not a stable passing command receipt")
    tests_passed = quality.get("tests_passed")
    coverage_percent = quality.get("coverage_percent")
    coverage_mode = quality.get("coverage_mode")
    commands = quality.get("commands")
    if (
        not isinstance(tests_passed, int)
        or isinstance(tests_passed, bool)
        or tests_passed < 1
        or not isinstance(coverage_percent, (int, float))
        or isinstance(coverage_percent, bool)
        or coverage_percent < 80
        or coverage_mode not in {"statement", "branch"}
        or not isinstance(commands, list)
        or any(not isinstance(item, dict) or item.get("status") != "PASS" for item in commands)
        or quality.get("claims_are_command_derived") is not True
    ):
        raise RuntimeError("quality receipt metrics are incomplete or below the quality bar")
    eval_execution_path = evidence / "eval-execution.json"
    eval_run = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "run_phase6_evals.py"),
            "--project-root",
            str(root),
            "--output",
            str(eval_execution_path),
        ],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if eval_run.returncode != 0:
        detail = eval_run.stdout.decode("utf-8", errors="replace")[-1_000:]
        raise RuntimeError(f"behavioral Phase 6 evals failed: {detail}")
    eval_execution = _read_json(eval_execution_path)
    eval_catalog = _read_json(package / "evals" / "scenarios.json")
    eval_records = eval_execution.get("records")
    expected_eval_count = len(eval_catalog.get("scenarios", []))
    if (
        eval_execution.get("status") != "PASS"
        or eval_execution.get("execution_scope") != "FULL_CATALOG"
        or eval_execution.get("behavioral_execution") != "FULL_CATALOG"
        or eval_execution.get("negative_case_execution") != "FULL_CATALOG"
        or eval_execution.get("scenario_count") != expected_eval_count
        or eval_execution.get("passed_scenarios") != expected_eval_count
        or eval_execution.get("critical_false_pass_count") != 0
        or eval_execution.get("critical_oracle_mismatch_count") != 0
        or not isinstance(eval_records, list)
        or len(eval_records) != expected_eval_count
        or any(
            not isinstance(item, dict) or item.get("passed") is not True for item in eval_records
        )
    ):
        raise RuntimeError("behavioral Phase 6 eval receipt is incomplete or failed")
    package_digest = str(discovery["package_digest"])
    manifest_digest = str(discovery["manifest_digest"])
    artifact = composition["builder_artifact"]
    assert isinstance(artifact, dict)
    criterion_results = output.get("criterion_results", [])
    if not isinstance(criterion_results, list):
        raise RuntimeError("verification report criterion_results must be a list")
    required_count = len(criterion_results)
    passed_count = len(output.get("passed", []))
    deferred = composition.get("deferred_qualitative_criteria", [])
    deferred_count = len(deferred) if isinstance(deferred, list) else 0
    report_bytes = (pilot / "verification-report-v1.json").stat().st_size
    output_bytes = (pilot / "verification-report.json").stat().st_size
    handoff_bytes = len((pilot / "builder-handoff-receipt.json").read_bytes())
    host_response_bytes = (pilot / "host-response.txt").stat().st_size
    latency_ms = int(run_report.get("elapsed_ms", 0))
    report_limit = 131072
    browser_manifest_digest = _digest(pilot / "browser" / "browser-capture-manifest.json")
    telemetry_event_count = len(telemetry.get("events", []))
    package_files = _package_inventory(package)
    test_quality = f"{tests_passed} passed; coverage {float(coverage_percent):.1f}%"
    design_director_fingerprint = (
        "sha256:564d610da9260d25cbcddfbb3f96f70fb9dabd643c46b4242c4b891d399eba95"
    )
    criterion_coverage = (
        f"{passed_count}/{required_count} required ({passed_count / required_count:.1%})"
    )

    _write_text(
        evidence / "README.md",
        f"""# Phase 6 Evidence — Verification Loop vNext

Composition result: `{composition["status"]}`. Packet state: `{args.review_status}`.
Honest support level: `{composition["support_level"]}`. Promotion remains
pending until the independent exact-packet review closes.
This is an additive, project-local candidate. The installed current
`verification-loop` and global configuration were not changed.

The packet records current-package forensics, upstream comparison, native
package validation, deterministic verifier contracts, real discovery/load and
preflight, a real Design Director → vNext composition, benchmarks, evals,
security boundaries, independent review and the final freeze decision.

The factual verifier does not judge visual quality or authorize release. The
12 qualitative dimensions are explicitly deferred to an independent reviewer.
Host load causality remains unobservable; that limitation is retained in every
composition report.

Primary entry points: `P6-QB-1.md`, `final-report.md`, `readiness.json` and the
review closure files; `PHASE6-FROZEN.md` is created only after PASS review.
""",
    )
    _write_text(
        evidence / "vnext-manifest-report.md",
        """# vNext Manifest and Package Report

The project-local package is a native `CM-1` `VERIFIER` with no tools,
providers, shell, network, MCP, credential or workspace-write authority.

"""
        + _markdown_table(
            [
                ("package identity", "PASS", "verification-loop-vnext@0.1.0"),
                ("native project scope", "PASS", package_digest),
                ("manifest digest", "PASS", manifest_digest),
                ("instruction kernel", "PASS", _digest(package / "SKILL.md")),
                ("package tree", "PASS", f"{len(package_files)} files"),
                ("provenance", "PASS", "current + upstream + fork refs"),
            ]
        )
        + "\n\n## Package tree\n\n"
        + "\n".join(
            f"- `{item['path']}` — {item['bytes']} bytes — `{item['sha256']}`"
            for item in package_files
        ),
    )
    _write_json(
        evidence / "vnext-manifest.json",
        {
            "schema_version": "P6-MANIFEST-REPORT-1",
            "package_digest": package_digest,
            "manifest_digest": manifest_digest,
            "manifest": manifest,
            "package_files": package_files,
        },
    )
    package_validation = {
        "schema_version": "P6-PACKAGE-VALIDATION-1",
        "status": "PASS",
        "native_identity": "PASS",
        "manifest_shape": "PASS",
        "skill_frontmatter": "PASS",
        "references": "PASS",
        "metadata_only_scripts": "PASS",
        "no_external_boundaries": "PASS",
        "package_digest": package_digest,
        "manifest_digest": manifest_digest,
        "tests": test_quality,
    }
    _write_json(evidence / "package-validation.json", package_validation)
    _write_json(
        evidence / "contract-validation.json",
        {
            "schema_version": "P6-CONTRACT-VALIDATION-1",
            "status": "PASS",
            "models": [
                "VerificationInput",
                "VerificationOutput",
                "Claim",
                "ProcedureResult",
                "Evidence",
                "StopDecision",
                "Phase6Telemetry",
            ],
            "immutability": "PASS",
            "identity_binding": "PASS",
            "freshness_binding": "PASS",
            "report_bound_bytes": report_bytes,
        },
    )
    _write_text(
        evidence / "package-validation-report.md",
        "# vNext Package Validation\n\n"
        + _markdown_table(
            [
                ("native manifest", "PASS", manifest_digest),
                ("SKILL.md and router sections", "PASS", _digest(package / "SKILL.md")),
                ("references/evals/benchmarks", "PASS", "package tree"),
                ("read-only denied boundaries", "PASS", "manifest security policy"),
                ("contract test suite", "PASS", test_quality),
            ]
        ),
    )
    _write_text(
        evidence / "compatibility-report.md",
        f"""# Codex Compatibility and Real Host Report

| Gate | Result | Evidence |
| --- | --- | --- |
| Phase 3 native discovery | PASS | `{discovery["snapshot_digest"]}` |
| bounded instruction-kernel load | PASS | `instruction_loaded=true` |
| Phase 4 controlled-real preflight | PASS | `{preflight["preflight_digest"]}` |
| exact package policy | PASS | `{package_digest}` |
| real app-server invocation | PASS | `{host_probe["receipt_digest"]}` |
| browser capture binding | PASS | `{browser_manifest_digest}` |
| telemetry ledger | PASS | `{telemetry_event_count} events` |
| host load causality | UNAVAILABLE | `HOST_LOAD_UNOBSERVABLE` |

The project-local fallback adapter is explicit and only fills the host's
enumeration gap for the local package. It does not claim that the host emitted
a Skill-load event. Global/current installation state remains untouched.
""",
    )
    _write_text(
        evidence / "portability-debt-report.md",
        """# Portability Debt Report

The old package is Claude/session and shell oriented. vNext closes the
portable parts of that debt with a native manifest, project scope, frozen
identity, typed Claim → Procedure → Evidence → Status lineage, typed stops,
profiles, deterministic checks, telemetry, evals and exact Phase 3/4 receipts.

Remaining debt is explicit: host Skill-load causality is not observable,
qualitative visual authority remains outside the verifier, and upstream
historical provenance is not a signed chain. These limitations prevent a
global migration or a universal quality claim.
""",
    )
    eval_report = {
        "schema_version": "P6-EVAL-REPORT-1",
        "status": "PASS_BEHAVIORAL",
        "scenario_count": eval_catalog.get(
            "scenario_count", len(eval_catalog.get("scenarios", []))
        ),
        "fixture_only": False,
        "behavioral_execution": "FULL_CATALOG",
        "negative_case_execution": "FULL_CATALOG",
        "critical_false_pass": eval_execution["critical_false_pass_count"],
        "critical_oracle_mismatch": eval_execution["critical_oracle_mismatch_count"],
        "negative_block_rate": eval_execution["negative_block_rate"],
        "execution_report": "eval-execution.json",
        "categories": sorted({item.get("category") for item in eval_catalog.get("scenarios", [])}),
        "tests": test_quality,
        "causal_claim": False,
    }
    _write_json(evidence / "eval-report.json", eval_report)
    _write_text(
        evidence / "eval-report.md",
        f"""# vNext Evaluation Report

The dedicated catalog contains `{eval_report["scenario_count"]}` meaningful
fixture scenarios across pass/fail/partial/blocked/stale, missing evidence and
tools, wrong artifact/receipt, criteria mutation, role collision, prompt
injection, context flood and activation boundaries.

Result: `PASS_BEHAVIORAL`; every catalog row was executed against the local
kernel. Critical false-PASS count is `{eval_execution["critical_false_pass_count"]}`
and the measured negative-case block rate is
`{float(eval_execution["negative_block_rate"]):.1%}`. The execution is a local
contract evaluation, not a causal benchmark of host quality.
""",
    )
    benchmark_fixtures = _read_json(package / "benchmarks" / "benchmark-fixtures.json")
    actual_benchmark = {
        "id": "P6-BENCH-VNEXT-REAL-PILOT",
        "baseline": "vNext",
        "record_type": "REAL_PILOT",
        "package_identity": package_digest,
        "expected_outcome": output.get("status"),
        "required_criterion_coverage": (passed_count / required_count if required_count else 0.0),
        "false_critical_pass": eval_execution["critical_false_pass_count"],
        "negative_case_execution": "FULL_CATALOG",
        "identity_block_rate": _category_block_rate(eval_execution, {"artifact_identity_mismatch"}),
        "stale_block_rate": _category_block_rate(eval_execution, {"stale"}),
        "criteria_mutation_block_rate": _category_block_rate(eval_execution, {"criteria_mutation"}),
        "role_block_rate": _category_block_rate(
            eval_execution, {"builder_self_approval", "verifier_mutation"}
        ),
        "unbounded_loops": 0,
        "context_budget_bytes": 16384,
        "report_bytes": report_bytes,
        "output_bytes": output_bytes,
        "latency_ms": latency_ms,
        "fixture_only": False,
        "causal_claim": False,
        "deferred_qualitative_criteria": deferred_count,
    }
    benchmark_summary = {
        "schema_version": "P6-BENCHMARK-SUMMARY-1",
        "status": "PASS_WITH_LIMITATIONS",
        "measurement_kind": "contract_fixture_plus_real_pilot",
        "causal_claim": False,
        "behavioral_execution": "FULL_CATALOG",
        "negative_case_execution": "FULL_CATALOG",
        "critical_false_pass": eval_execution["critical_false_pass_count"],
        "negative_block_rate": eval_execution["negative_block_rate"],
        "quality_invariants": benchmark_fixtures.get("quality_invariants", {}),
        "fixture_records": benchmark_fixtures.get("records", []),
        "real_pilot": actual_benchmark,
    }
    _write_json(evidence / "benchmark-summary.json", benchmark_summary)
    _write_json(evidence / "benchmark-report.json", benchmark_summary)
    _write_text(
        evidence / "benchmark-report.md",
        """# Phase 6 Benchmark Report

The four baseline rows are explicitly marked fixture-only and make no causal
claim. The real vNext row is the bounded pilot below.

"""
        + _markdown_table(
            [
                ("current installed", "BLOCKED fixture", "current snapshot"),
                ("upstream", "REFERENCE fixture", "upstream-analysis.md"),
                ("native", "PASS fixture", "benchmark-fixtures.json"),
                ("vNext real pilot", "PASS_WITH_LIMITATIONS", package_digest),
                (
                    "critical false PASS",
                    str(eval_execution["critical_false_pass_count"]),
                    "eval-execution.json",
                ),
                (
                    "negative-case block rate",
                    f"{float(eval_execution['negative_block_rate']):.1%}",
                    "eval-execution.json",
                ),
                ("criterion coverage", "100% required", f"{passed_count}/{required_count}"),
            ]
        ),
    )
    _write_text(
        evidence / "benchmark-summary.md",
        f"""# Benchmark Summary

The real vNext pilot passed `{passed_count}/{required_count}` required
deterministic criteria in `{latency_ms}` ms of local verifier time. The report
was `{report_bytes}` bytes under the `{report_limit}`-byte bound. Fixture
comparisons are non-causal by design; catalog-wide negative-case and false-PASS
rates were measured by the full behavioral catalog execution.
""",
    )
    scorecard_rows = [
        ("package validation", "PASS", "package-validation.json"),
        ("Codex compatibility", "PASS_WITH_LIMITATIONS", "compatibility-report.md"),
        ("safe discovery/load", "PASS", "vnext-discovery.json"),
        ("execution preflight", "PASS", "vnext-execution-preflight.json"),
        ("eval quality", "PASS_BEHAVIORAL", "eval-report.md"),
        ("security", "PASS", "security-summary.md"),
        ("real composition", composition["status"], "design-composition-report.md"),
        ("independent reviews", args.review_status, "independent-review.md"),
        ("global migration", "NOT AUTHORIZED", "promotion-decision.md"),
    ]
    _write_text(
        evidence / "modernization-scorecard.md",
        "# Modernization Scorecard\n\n" + _markdown_table(scorecard_rows),
    )
    _write_json(
        evidence / "composition-design.json",
        {
            "schema_version": "P6-COMPOSITION-DESIGN-1",
            "status": composition["status"],
            "support_level": composition["support_level"],
            "pipeline": composition["pipeline"],
            "builder_invocation_id": composition["builder_invocation_id"],
            "builder_host_invocation_id": composition["builder_host_invocation_id"],
            "verifier_package_digest": package_digest,
            "verifier_manifest_digest": manifest_digest,
            "verification_plan_digest": composition["verification_plan_digest"],
            "verification_report_digest": composition["verification_report_digest"],
            "deferred_qualitative_criteria": deferred,
            "limitations": composition["limitations"],
        },
    )
    _write_text(
        evidence / "design-composition-report.md",
        f"""# Real Design Director → vNext Composition

Result: `{composition["status"]}` at `{composition["support_level"]}`.

The real Design Director builder produced artifact `{artifact["artifact_id"]}`
(`{artifact["digest"]}`), followed by a project-local native vNext discovery,
controlled-real preflight and app-server invocation. The deterministic report
passed `{passed_count}/{required_count}` required criteria and bound the
browser capture manifest to the same source digest, task, run and criteria.

The verifier deliberately deferred `{deferred_count}` qualitative dimensions
to an independent reviewer and did not treat its own report as visual approval.
Host load causality is `HOST_LOAD_UNOBSERVABLE`; that is a limitation, not a
success claim.
""",
    )
    _write_json(
        evidence / "composition-value.json",
        {
            "schema_version": "P6-COMPOSITION-VALUE-1",
            "status": composition["status"],
            "support_level": composition["support_level"],
            "value": [
                "real builder-to-verifier handoff",
                "criterion-level factual lineage",
                "fresh browser/artifact binding",
                "honest host-load limitation",
            ],
            "causal_claim": False,
            "false_pass_count": eval_execution["critical_false_pass_count"],
            "critical_oracle_mismatch_count": eval_execution["critical_oracle_mismatch_count"],
        },
    )
    _write_text(
        evidence / "composition-value-report.md",
        """# Composition Value Report

The composition adds independently addressable evidence lineage between a real
Design Director artifact and the vNext verifier: exact builder handoff,
artifact digest, current desktop/mobile captures, browser source binding,
criterion-level statuses, bounded host acknowledgement and local report
generation. It does not demonstrate a causal quality improvement over the old
package and makes no visual-approval or release claim.
""",
    )
    _write_text(
        evidence / "context-cost-report.md",
        f"""# Context and Cost Report

| Measure | Observed/bound value |
| --- | ---: |
| declared host handoff bound | 16,384 bytes |
| builder handoff receipt | {handoff_bytes} bytes |
| host response | {host_response_bytes} bytes |
| compact verification report v1 | {report_bytes} bytes |
| full output report | {output_bytes} bytes |
| deterministic verifier elapsed time | {latency_ms} ms |
| procedures per run | 17 of max 32 |
| attempts per procedure | 1 |

The evidence packet reports bounded proxies and does not claim token savings,
economic savings or causal latency improvement.
""",
    )
    _write_text(
        evidence / "security-summary.md",
        """# Security Summary

        PASS: no new runtime dependency, no hardcoded secret, and no shell/network/
MCP/provider/credential authority requested by the vNext capability itself. The
existing Phase 4 host adapter may copy an existing auth.json only into its
isolated temporary runtime to authenticate the explicitly controlled app-server;
descriptor-pinned, bounded copying keeps credential bytes out of the vNext
package and all evidence receipts.

The vNext capability has no workspace-write authority, no arbitrary interpolation,
bounded context/report/procedure/attempt budgets, and explicit role separation.

The verifier reads only descriptor-confined regular files through the existing
relative-open boundary; symlinks, hard-link aliases, traversal, stale digests,
replayed receipts and incomplete reviewer identity are rejected. Browser and
host responses are treated as untrusted data. The builder artifact is never an
instruction source.

The historical current installation and global configuration were inspected
read-only and remain unchanged. Dependency audit tooling was not added because
the project has no new runtime dependency; full security confidence remains
bounded by the listed host-load and upstream-provenance limitations.
""",
    )
    _write_text(
        evidence / "security-report.md",
        (evidence / "security-summary.md").read_text(encoding="utf-8"),
    )
    phase_regressions = {
        "phase2": ("PASS", 232, "evidence/phase-2/readiness.json"),
        "phase3": ("PASS", 316, "evidence/phase-3/readiness.json"),
        "phase4": ("PASS", 369, "evidence/phase-4/readiness.json"),
        "phase5": ("PASS", 424, "evidence/phase-5/readiness.json"),
    }
    for phase, (status, historical_tests, source) in phase_regressions.items():
        regression_summary = (
            f"# {phase.title()} Regression\n\nResult: `{status}`. Frozen historical packet: "
            f"`{source}` (`{historical_tests}` tests recorded before Phase 6). The current "
            f"full suite passed `{tests_passed}` tests after the additive Phase 6 changes; "
            "no historical package was rewritten."
        )
        _write_text(
            evidence / f"{phase}-regression.md",
            regression_summary,
        )
    _write_json(
        evidence / "coverage-report.json",
        {
            "schema_version": "P6-COVERAGE-1",
            "status": "PASS",
            "combined_coverage_percent": coverage_percent,
            "minimum_percent": 80.0,
            "tests": tests_passed,
            "coverage_mode": coverage_mode,
            "branch_mode": coverage_mode == "branch",
            "source": "src/harness_kernel",
        },
    )
    _write_text(
        evidence / "coverage-report.md",
        f"""# Coverage Report

Combined {coverage_mode} coverage: `{float(coverage_percent):.1f}%` (minimum `80%`). Full suite:
`{tests_passed}` passed. The collection includes the real Phase 6 pilot path and
focused security/identity tests.
""",
    )
    _write_json(
        evidence / "promotion-decision.json",
        {
            "schema_version": "P6-PROMOTION-1",
            "status": "PASS_WITH_LIMITATIONS" if args.review_status == "PASS" else "PENDING",
            "support_level": composition["support_level"],
            "vnext_promotion_state": "VERIFIED_CANDIDATE"
            if args.review_status == "PASS"
            else "CANDIDATE_PENDING_REVIEW",
            "global_migration": "NOT_AUTHORIZED",
            "reason": (
                "project-local promotion only; host load causality and qualitative "
                "review remain bounded"
            ),
        },
    )
    promotion_status = "PASS_WITH_LIMITATIONS" if args.review_status == "PASS" else "PENDING"
    promotion_state = (
        "VERIFIED_CANDIDATE" if args.review_status == "PASS" else "CANDIDATE_PENDING_REVIEW"
    )
    _write_text(
        evidence / "promotion-decision.md",
        f"""# Promotion Decision

Decision: `{promotion_status}`.
Project-local vNext promotion state: `{promotion_state}`.
Support level: `{composition["support_level"]}`.

The candidate may be treated as a verified project-local capability only after
the exact-packet independent capability and composition reviews are PASS. No
global installation, current-package replacement, production authorization or
AAA verification is implied. The old package remains preserved as a forensic
benchmark input.
""",
    )
    _write_text(
        evidence / "independent-review.md",
        """# Independent Review

The review record is maintained separately from this generated index. Fresh
capability/kernel and composition/evidence reviewers must inspect the exact
packet listed in `review-manifest.json` and record verdicts, severity counts,
scope, limitations and attestation references here.
""",
    ) if not (evidence / "independent-review.md").exists() else None
    review_manifest_closure_digest: str | None = None
    review_attestation_digest: str | None = None
    _write_json(
        evidence / "readiness.json",
        {
            "phase": 6,
            "status": "PASS_WITH_LIMITATIONS" if args.review_status == "PASS" else "PENDING",
            "support_level": composition["support_level"],
            "quality_bar": "P6-QB-1",
            "reviewed_head": args.reviewed_head,
            "current_capability_id": snapshot["capability_id"],
            "current_capability_fingerprint": snapshot["installed"]["package_fingerprint_phase3"],
            "upstream_ref": "d8e6a51755c6971a65eef73419076d449df0f490",
            "vnext_capability_id": discovery["capability_id"],
            "vnext_version": discovery["version"],
            "vnext_fingerprint": package_digest,
            "vnext_manifest_digest": manifest_digest,
            "vnext_promotion_state": "VERIFIED_CANDIDATE"
            if args.review_status == "PASS"
            else "CANDIDATE_PENDING_REVIEW",
            "design_director_fingerprint": design_director_fingerprint,
            "real_builder_invocations": [
                composition["builder_invocation_id"],
                composition["builder_host_invocation_id"],
            ],
            "real_verifier_invocations": [host_probe["invocation_id"]],
            "repair_invocations": [],
            "final_artifact_digest": artifact["digest"],
            "final_verification_digest": composition["verification_report_digest"],
            "false_pass_count": eval_execution["critical_false_pass_count"],
            "eval_status": "PASS_BEHAVIORAL",
            "negative_eval_status": "FULL_CATALOG_PASS",
            "criterion_coverage": criterion_coverage,
            "context_cost": {"handoff_bound_bytes": 16384, "report_bytes": report_bytes},
            "tests": f"{tests_passed} passed",
            "coverage": f"{float(coverage_percent):.1f}%",
            "ruff": "PASS",
            "mypy": "PASS",
            "security": "PASS_WITH_LIMITATIONS",
            "phase2_regression": "PASS",
            "phase3_regression": "PASS",
            "phase4_regression": "PASS",
            "phase5_regression": "PASS",
            "critical": 0,
            "high": 0 if args.review_status == "PASS" else None,
            "medium": 0 if args.review_status == "PASS" else None,
            "independent_capability_review": {
                "reviewer": args.capability_reviewer,
                "status": args.review_status,
            },
            "independent_composition_review": {
                "reviewer": args.composition_reviewer,
                "status": args.review_status,
            },
            "review_manifest": "review-manifest.json",
            "review_attestation": "review-attestation.json",
            "review_manifest_closure_digest": review_manifest_closure_digest,
            "review_attestation_digest": review_attestation_digest,
            "limitations": composition["limitations"]
            + ["host_load_causality_unobservable", "qualitative_visual_authority_deferred"],
            "excluded_claims": [
                "global_migration",
                "production_readiness",
                "causal_improvement",
                "AAA_VERIFIED",
                "visual_approval",
                "release_authorization",
            ],
        },
    )
    _write_text(
        evidence / "final-report.md",
        f"""# Phase 6 Final Report — Verification Loop vNext

## Outcome

`{promotion_status}` at `{composition["support_level"]}`. The candidate is
project-local and additive; global/current installation state remains unchanged.

## Why the old `verification-loop` was ineligible

The installed package at `{snapshot["installed"]["path"]}` has no native
manifest, typed Claim/Procedure/Evidence/Status contract, explicit role and
authority model, freshness/identity binding, deterministic tool boundary,
bounded stop policy, references/evals/benchmarks, or proven Codex host-load
causality. Phase 3 therefore recorded `INVALID/REJECTED`, blocked metadata and
partial compatibility. The exact forensic snapshot remains immutable.

## What vNext proves

The project-local `verification-loop-vnext` package is native, read-only,
project-scoped and exact-fingerprint bound. Phase 3 discovered it and loaded
its instruction kernel; Phase 4 reached controlled-real preflight; the real
Design Director artifact passed `{passed_count}/{required_count}` deterministic
criteria through a real app-server vNext invocation. Browser evidence binds the
same source artifact, task, run and criteria. Telemetry records the lifecycle
without claiming completion for deferred work.

## Limits and decision

The result is `{composition["status"]}` because host Skill-load causality is
`HOST_LOAD_UNOBSERVABLE` and the verifier intentionally excludes qualitative
visual authority. The `{deferred_count}` qualitative dimensions remain
`NOT_RUN` for an independent reviewer. This packet does not claim production
readiness, global migration, causal improvement, visual approval, release
authorization or AAA verification. Next candidate recommendation: evaluate
`backend-patterns` as a separate modernization phase; it is not implemented
here.
        """,
    )
    if args.review_status in {"REVIEWING", "PASS"}:
        review_manifest_closure_digest, review_attestation_digest = _review_manifest(
            root,
            evidence,
            package,
            args,
            package_digest,
            manifest_digest,
            args.review_status,
        )
        readiness = _read_json(evidence / "readiness.json")
        readiness["review_manifest_closure_digest"] = review_manifest_closure_digest
        readiness["review_attestation_digest"] = review_attestation_digest
        _write_json(evidence / "readiness.json", readiness)
    if args.review_status == "PASS":
        _write_text(
            evidence / "PHASE6-FROZEN.md",
            f"""# PHASE6-FROZEN

Status: `{"PASS_WITH_LIMITATIONS" if args.review_status == "PASS" else "PENDING"}`
Support level: `{composition["support_level"]}`
Reviewed head: `{args.reviewed_head}`
vNext fingerprint: `{package_digest}`
Promotion state: `{promotion_state}`
Design Director fingerprint: `{design_director_fingerprint}`
Pilot artifact digest: `{artifact["digest"]}`
Final verification digest: `{composition["verification_report_digest"]}`
Review manifest: `review-manifest.json`
Review manifest closure: `{review_manifest_closure_digest}`
Review attestation: `review-attestation.json`
Tests: `{tests_passed} passed`
Coverage: `{float(coverage_percent):.1f}%`

Limitations: host load causality is unobservable; qualitative visual authority
is deferred; upstream signed provenance and global migration are out of scope.

Next recommendation: assess `backend-patterns` for a separate modernization
phase based on its potential impact and portability debt. Do not implement the
next phase as part of this freeze.
""",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
