from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "verification-loop-vnext"
PACKAGE_SCENARIOS = PACKAGE_ROOT / "evals" / "scenarios.json"
TEST_SCENARIOS = PROJECT_ROOT / "tests" / "fixtures" / "phase6" / "scenarios.json"
PACKAGE_BENCHMARKS = PACKAGE_ROOT / "benchmarks" / "benchmark-fixtures.json"
TEST_BENCHMARKS = PROJECT_ROOT / "tests" / "fixtures" / "phase6" / "benchmark-fixtures.json"

SCENARIO_ID = re.compile(r"^P6-SC-\d{3}$")
REQUIRED_CATEGORIES = {
    "pass",
    "fail",
    "partial",
    "blocked",
    "stale",
    "missing_evidence",
    "missing_tool",
    "artifact_identity_mismatch",
    "criteria_mutation",
    "builder_self_approval",
    "verifier_mutation",
    "prompt_injection",
    "context_flood",
    "path_traversal",
    "overactivation",
    "underactivation",
}
EXPECTED_BY_CATEGORY = {
    "pass": "PASS",
    "fail": "FAIL",
    "partial": "PARTIAL",
    "blocked": "BLOCKED",
    "stale": "STALE",
    "missing_evidence": "BLOCKED",
    "missing_tool": "BLOCKED",
    "artifact_identity_mismatch": "BLOCKED",
    "criteria_mutation": "BLOCKED",
    "builder_self_approval": "BLOCKED",
    "verifier_mutation": "BLOCKED",
    "prompt_injection": "BLOCKED",
    "context_flood": "BLOCKED",
    "path_traversal": "BLOCKED",
    "overactivation": "BLOCKED",
    "underactivation": "PASS",
}
BENCHMARK_IDS = {
    "P6-BENCH-CURRENT",
    "P6-BENCH-UPSTREAM",
    "P6-BENCH-NATIVE",
    "P6-BENCH-VNEXT",
}


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase6_scenario_catalog_is_stable_and_meaningful() -> None:
    package_catalog = _load(PACKAGE_SCENARIOS)
    fixture_catalog = _load(TEST_SCENARIOS)
    assert package_catalog == fixture_catalog
    assert package_catalog["schema_version"] == "P6-EVAL-1"
    scenarios = package_catalog["scenarios"]
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 30

    ids = [scenario["id"] for scenario in scenarios]
    assert len(ids) == len(set(ids))
    assert all(SCENARIO_ID.fullmatch(identifier) for identifier in ids)
    assert ids == [f"P6-SC-{index:03d}" for index in range(1, len(ids) + 1)]
    assert {scenario["category"] for scenario in scenarios} >= REQUIRED_CATEGORIES


def test_phase6_scenarios_have_outcomes_oracles_and_required_criterion_bindings() -> None:
    scenarios = _load(PACKAGE_SCENARIOS)["scenarios"]
    allowed_outcomes = {"PASS", "FAIL", "PARTIAL", "BLOCKED", "STALE", "NOT_RUN", "UNKNOWN"}

    for scenario in scenarios:
        assert scenario["expected_outcome"] in allowed_outcomes
        assert scenario["oracle"].strip()
        assert scenario["rationale"].strip()
        assert (
            scenario["required_criterion_ids"]
            or scenario.get("criterion_binding") == "NONE_BY_DESIGN"
        )
        assert scenario["input_identity"]
        assert scenario["evidence_refs"] or scenario.get("evidence_binding") == "NONE_BY_DESIGN"
        assert scenario["critical"] in {True, False}
        assert scenario["expected_outcome"] == EXPECTED_BY_CATEGORY[scenario["category"]]


def test_phase6_negative_scenarios_are_explicitly_fail_closed() -> None:
    scenarios = _load(PACKAGE_SCENARIOS)["scenarios"]
    negative_categories = REQUIRED_CATEGORIES - {"pass", "partial", "underactivation"}
    negative = [scenario for scenario in scenarios if scenario["category"] in negative_categories]

    assert negative
    assert all(
        scenario["expected_outcome"] in {"FAIL", "BLOCKED", "STALE"} for scenario in negative
    )
    assert all(scenario["oracle"][0].isupper() for scenario in negative)


def test_phase6_benchmark_fixtures_cover_all_baselines_and_quality_invariants() -> None:
    package_benchmarks = _load(PACKAGE_BENCHMARKS)
    fixture_benchmarks = _load(TEST_BENCHMARKS)
    assert package_benchmarks == fixture_benchmarks
    assert package_benchmarks["schema_version"] == "P6-BENCH-1"
    records = package_benchmarks["records"]
    assert {record["id"] for record in records} == BENCHMARK_IDS

    for record in records:
        assert record["false_critical_pass"] == 0
        assert record["required_criterion_coverage"] >= 0.95
        assert record["identity_block_rate"] == 1.0
        assert record["stale_block_rate"] == 1.0
        assert record["criteria_mutation_block_rate"] == 1.0
        assert record["role_block_rate"] == 1.0
        assert record["unbounded_loops"] == 0
        assert record["causal_claim"] is False
        assert record["fixture_only"] is True


def test_phase6_eval_metadata_matches_catalog_and_benchmark_metadata() -> None:
    scenarios = _load(PACKAGE_SCENARIOS)["scenarios"]
    eval_metadata = _load(PACKAGE_ROOT / "eval-metadata.json")
    benchmark_metadata = _load(PACKAGE_ROOT / "benchmark-metadata.json")

    assert eval_metadata["scenario_count"] == len(scenarios)
    assert set(eval_metadata["required_categories"]) == REQUIRED_CATEGORIES
    assert eval_metadata["stable_id_pattern"] == "P6-SC-NNN"
    assert benchmark_metadata["fixture_ids"] == sorted(BENCHMARK_IDS)
