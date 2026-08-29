from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

from phase2_support import authorized_kernel
from test_contracts import all_records

from harness_kernel.assurance import AssuranceDecision, assure_quality, create_critique
from harness_kernel.authority import AuthorityScope
from harness_kernel.graph import GraphStatus
from harness_kernel.models import (
    ExecutionGraph,
    InvocationStatus,
    NodeBudget,
)
from harness_kernel.providers import (
    DeterministicFailureProvider,
    DeterministicPartialProvider,
    DeterministicSuccessProvider,
    ProviderRegistry,
)
from harness_kernel.verification import stale_verification, verify_provider_result

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
            relative_path, function_name = proof.split("::", 1)
            proof_path = PROJECT_ROOT / relative_path
            assert proof_path.is_file()
            tree = ast.parse(proof_path.read_text(encoding="utf-8"))
            assert any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == function_name
                for node in ast.walk(tree)
            )


def _golden_graph(
    *, task_id: str, run_id: str, first_provider: str = "local.success"
) -> ExecutionGraph:
    original = all_records()[2]
    first = replace(
        original.nodes[0],
        node_id="NODE-1",
        capability_id="local.direct",
        provider_id=first_provider,
        output_contract="LocalExecutionResult",
        acceptance_refs=("P2-EXECUTION",),
        node_status=InvocationStatus.REQUESTED,
    )
    second = replace(
        first,
        node_id="NODE-2",
        provider_id="local.success",
        depends_on=("NODE-1",),
    )
    return replace(
        original,
        task_id=task_id,
        run_id=run_id,
        graph_status=GraphStatus.READY,
        nodes=(first, second),
        edges=(),
        graph_owner="orchestrator",
        acceptance_refs=("P2-EXECUTION",),
        graph_budget=NodeBudget(tokens=2_000, duration_ms=10_000),
        merge_policy="PRESERVE_AND_ESCALATE",
    )


def _run_golden_scenario(scenario_id: str, tmp_path: Path) -> tuple[str, int]:
    task_id = f"TASK-GOLDEN-{scenario_id}"
    run_id = f"RUN-GOLDEN-{scenario_id}"
    if scenario_id == "A":
        result = authorized_kernel(tmp_path).run(
            "Change one local label", task_id=task_id, run_id=run_id, provider_id="local.success"
        )
    elif scenario_id == "B":
        expired = AuthorityScope(
            owner="golden-policy",
            actor="golden-runner",
            scopes=(f"task:{task_id}", "capability:local.success"),
            decisions=("TRANSITION",),
            subject_owner="golden-policy",
            operations=("execute",),
            issued_at="2026-08-28T12:00:00Z",
            expires_at="2026-08-28T13:00:00Z",
        )
        result = authorized_kernel(tmp_path).run(
            "Change one local label",
            task_id=task_id,
            run_id=run_id,
            provider_id="local.success",
            authority=expired,
            persist=False,
        )
    elif scenario_id == "C":
        result = authorized_kernel(tmp_path).run(
            "Run the local graph",
            graph=_golden_graph(task_id=task_id, run_id=run_id),
        )
    elif scenario_id == "D":
        result = authorized_kernel(
            tmp_path,
            providers=(
                ProviderRegistry()
                .register(DeterministicFailureProvider())
                .register(DeterministicSuccessProvider())
            ),
        ).run(
            "Run the local graph",
            graph=_golden_graph(task_id=task_id, run_id=run_id, first_provider="local.failure"),
        )
    elif scenario_id == "E":
        result = authorized_kernel(
            tmp_path,
            providers=ProviderRegistry().register(
                DeterministicSuccessProvider(delay_ms=200, duration_ms=200)
            ),
        ).run(
            "Time out a slow local fixture",
            task_id=task_id,
            run_id=run_id,
            provider_id="local.success",
            timeout_ms=15,
        )
    elif scenario_id == "F":
        calls = 0

        def cancelled() -> bool:
            nonlocal calls
            calls += 1
            return calls >= 2

        result = authorized_kernel(
            tmp_path,
            providers=ProviderRegistry().register(
                DeterministicSuccessProvider(delay_ms=200, duration_ms=200)
            ),
        ).run(
            "Cancel a slow local fixture",
            task_id=task_id,
            run_id=run_id,
            provider_id="local.success",
            cancelled=cancelled,
            timeout_ms=1_000,
        )
    elif scenario_id == "G":
        result = authorized_kernel(
            tmp_path,
            providers=ProviderRegistry().register(
                DeterministicSuccessProvider(result_provider_id="forged.provider")
            ),
        ).run(
            "Change one local label",
            task_id=task_id,
            run_id=run_id,
            provider_id="local.success",
        )
    elif scenario_id == "H":
        result = authorized_kernel(
            tmp_path,
            providers=ProviderRegistry().register(DeterministicPartialProvider()),
        ).run(
            "Preserve a partial local result",
            task_id=task_id,
            run_id=run_id,
            provider_id="local.partial",
        )
    elif scenario_id == "I":
        result = authorized_kernel(tmp_path).run(
            "Change one local label",
            task_id=task_id,
            run_id=run_id,
            provider_id="local.success",
            stop_before_run=True,
        )
    elif scenario_id == "J":
        result = authorized_kernel(
            tmp_path,
            providers=(
                ProviderRegistry()
                .register(DeterministicFailureProvider())
                .register(DeterministicSuccessProvider(provider_id="local.repair"))
            ),
        ).run(
            "Repair the local fixture",
            task_id=task_id,
            run_id=run_id,
            provider_id="local.failure",
            repair_provider_id="local.repair",
            max_repairs=1,
        )
    elif scenario_id == "K":
        result = authorized_kernel(
            tmp_path,
            providers=ProviderRegistry().register(DeterministicFailureProvider()),
        ).run(
            "Change one local label after explicit repair attempts",
            task_id=task_id,
            run_id=run_id,
            provider_id="local.failure",
            repair_provider_id="local.failure",
            max_repairs=2,
        )
    elif scenario_id == "L":
        result = authorized_kernel(tmp_path).run(
            "Change one local label",
            task_id=task_id,
            run_id=run_id,
            provider_id="local.success",
        )
        outcome = verify_provider_result(
            result.invocations[0], result.provider_results[-1], result.artifacts[0]
        )
        stale = stale_verification(outcome)
        critique = create_critique(stale.report)
        assurance = assure_quality(stale.report, critique)
        assert assurance.decision is AssuranceDecision.FAILED
        return "FAILED", len(result.provider_results)
    else:
        raise AssertionError(f"unknown golden scenario {scenario_id}")
    return str(result.status.value), len(result.provider_results)


def test_phase2_golden_scenarios_execute_public_kernel_and_match_oracles(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))

    for scenario in document["scenarios"]:
        status, provider_calls = _run_golden_scenario(scenario["id"], tmp_path)
        assert status == scenario["expected_status"], scenario["name"]
        assert provider_calls == scenario["provider_calls"], scenario["name"]
