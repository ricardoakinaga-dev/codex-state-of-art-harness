from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "golden" / "phase2-scenarios.json"


def test_phase2_golden_fixture_is_materialized_and_points_to_executable_proofs() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert document["schema_version"] == "P2-GOLDEN-1"
    scenarios = document["scenarios"]
    assert [item["id"] for item in scenarios] == list("ABCDEFGHIJKL")
    assert all(item["expected_status"] for item in scenarios)
    assert all(isinstance(item["provider_calls"], int) for item in scenarios)
    for item in scenarios:
        for proof in item["proof_tests"]:
            relative_path = proof.split("::", 1)[0]
            assert (PROJECT_ROOT / relative_path).is_file()
