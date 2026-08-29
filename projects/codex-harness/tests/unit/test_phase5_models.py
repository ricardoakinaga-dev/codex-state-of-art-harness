from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from phase5_support import make_task

from harness_kernel.phase5_models import (
    AcceptanceCriteria,
    ArtifactPacket,
    CompositionReceipt,
    FindingSeverity,
    Phase5Budget,
    Phase5Role,
    Phase5Status,
    VisualCritique,
)


def test_phase5_budget_is_finite_and_immutable() -> None:
    budget = Phase5Budget()
    assert budget.max_builder_invocations == 2
    assert budget.max_repairs == 1
    with pytest.raises(ValueError):
        Phase5Budget(max_repairs=2)
    with pytest.raises(ValueError):
        Phase5Budget(max_builder_invocations=3)
    with pytest.raises(ValueError):
        Phase5Budget(max_context_bytes=65_536)
    with pytest.raises(FrozenInstanceError):
        budget.max_builder_invocations = 3  # type: ignore[misc]


def test_phase5_criteria_reject_bad_viewports_and_empty_dimensions() -> None:
    with pytest.raises(ValueError):
        AcceptanceCriteria(render_viewports=((0, 900),))
    with pytest.raises(ValueError):
        AcceptanceCriteria(dimensions=())


def test_task_and_artifact_are_bound_to_the_same_immutable_contract(tmp_path) -> None:
    task = make_task(tmp_path)
    artifact = ArtifactPacket.from_content(
        artifact_id="ART-P5-V1",
        version="artifact_v1",
        path=task.workspace + "/artifacts/artifact_v1/index.html",
        content="<!doctype html><main>Northline</main>",
        producer_capability="design-director",
        invocation_id="INV-P5-1",
        task=task,
    )
    assert artifact.acceptance_digest == task.criteria.digest
    assert artifact.digest.startswith("sha256:")
    assert artifact.source_kind == "HOST_RESPONSE_DERIVED"
    with pytest.raises(ValueError):
        ArtifactPacket.from_content(
            artifact_id="ART-P5-V1",
            version="artifact_v1",
            path="/tmp/outside/index.html",
            content="x",
            producer_capability="design-director",
            invocation_id="INV-P5-1",
            task=task,
        )


def test_blind_critique_requires_separation_and_current_artifact(tmp_path) -> None:
    task = make_task(tmp_path)
    critique = VisualCritique(
        benchmark_id="P5-DESIGN-1",
        run_id=task.run_id,
        inspection_id="INS-P5-1",
        artifact_digest="sha256:" + "4" * 64,
        independence="INDEPENDENT",
        blinded=True,
        builder_rationale_withheld=True,
        self_score_withheld=True,
        packet_digest="sha256:" + "5" * 64,
        verdict=Phase5Status.PASS_WITH_LIMITATIONS,
        overall_score=86.0,
        evidence_confidence="HIGH",
        dimension_scores={"ART_DIRECTION": 8.0},
        findings=(),
        top_corrections=(),
        evidence_missing=(),
    )
    assert critique.is_independent is True
    with pytest.raises(ValueError):
        VisualCritique(
            benchmark_id="P5-DESIGN-1",
            run_id=task.run_id,
            inspection_id="INS-P5-2",
            artifact_digest=critique.artifact_digest,
            independence="SELF",
            blinded=False,
            builder_rationale_withheld=False,
            self_score_withheld=False,
            packet_digest=critique.packet_digest,
            verdict=Phase5Status.PASS,
            overall_score=99.0,
            evidence_confidence="HIGH",
            dimension_scores={},
            findings=(),
            top_corrections=(),
            evidence_missing=(),
        )


def test_receipt_rejects_unknown_graph_or_role() -> None:
    assert Phase5Role.DESIGN_BUILDER.value == "DESIGN_BUILDER"
    with pytest.raises(ValueError):
        CompositionReceipt(
            task_id="TASK-P5",
            run_id="RUN-P5",
            status=Phase5Status.PASS,
            graph=("DESIGN_BUILDER", "ARBITRARY_NODE"),
            events=(),
            builder_invocations=1,
            verifier_invocations=1,
            critic_invocations=1,
            repair_invocations=0,
            artifact_versions=(),
            stale_evidence=(),
            external_verifier="BLOCKED",
        )


def test_finding_severity_preserves_polish_as_non_blocking() -> None:
    assert FindingSeverity.POLISH.value == "POLISH"
    assert Phase5Status.BLOCKED.value == "BLOCKED"
