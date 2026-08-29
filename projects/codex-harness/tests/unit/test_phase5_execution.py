from __future__ import annotations

import json

import pytest
from phase5_support import make_task, valid_html

from harness_kernel.phase5_execution import (
    BuilderResponse,
    CompositionRunner,
    run_bounded_composition,
)
from harness_kernel.phase5_models import Phase5Status, VisualCritique


def _verifier(_task, artifact, *, version):
    from harness_kernel.phase5_models import StructuralVerification

    return StructuralVerification(
        "VER-TEST",
        version,
        artifact.digest,
        Phase5Status.PASS,
        ("test_verifier",),
        (),
        (),
    )


def _response(task, invocation_id: str = "INV-P5-1") -> BuilderResponse:
    return BuilderResponse(
        status=Phase5Status.PASS,
        invocation_id=invocation_id,
        final_message=json.dumps(
            {"artifact_filename": "index.html", "artifact_html": valid_html()}
        ),
        host_invoked=True,
        load_observation="HOST_LOAD_UNOBSERVABLE",
    )


def _critique(packet, *, verdict: str, findings=(), **extra):
    payload = {
        "benchmark_id": packet.benchmark_id,
        "run_id": packet.run_id,
        "inspection_id": "INS-P5-TEST",
        "artifact_digest": packet.artifact.digest,
        "packet_digest": packet.packet_digest,
        "independence": "INDEPENDENT",
        "blinded": True,
        "builder_rationale_withheld": True,
        "self_score_withheld": True,
        "verdict": verdict,
        "findings": list(findings),
    }
    payload.update(extra)
    return payload


def test_runner_uses_fixed_order_and_never_invokes_repair_without_material_gap(tmp_path) -> None:
    task = make_task(tmp_path)
    calls: list[str] = []

    def builder(_task, attempt):
        calls.append(f"builder:{attempt}")
        return _response(task)

    def critic(packet):
        calls.append("critic")
        return _critique(packet, verdict="PASS", overall_score=92)

    result = run_bounded_composition(task, builder=builder, critic=critic, verifier=_verifier)
    assert result.status == Phase5Status.PASS
    assert calls == ["builder:1", "critic"]
    assert result.receipt.repair_invocations == 0


def test_runner_repairs_once_then_invalidates_old_verification(tmp_path) -> None:
    task = make_task(tmp_path)
    builder_calls = 0
    repair_corrections: list[str] = []

    def builder(_task, attempt):
        nonlocal builder_calls
        builder_calls += 1
        return _response(task, f"INV-P5-{attempt}")

    def repair_builder(_task, attempt, correction):
        repair_corrections.append(correction)
        return _response(task, f"INV-P5-REPAIR-{attempt}")

    def critic(packet):
        if packet.artifact.version == "artifact_v1":
            return _critique(
                packet,
                verdict="FAIL",
                overall_score=72,
                findings=[
                    {
                        "id": "V-001",
                        "location": "Hero",
                        "expected": "Product-specific visual language",
                        "observed": "Generic hero",
                        "severity": "HIGH",
                        "evidence": "artifact_v1",
                        "status": "OPEN",
                    }
                ],
                top_corrections=["Replace generic visual with the orbital clinical mark"],
            )
        return _critique(packet, verdict="PASS", overall_score=91)

    result = CompositionRunner().run(
        task,
        builder=builder,
        repair_builder=repair_builder,
        critic=critic,
        verifier=_verifier,
    )
    assert result.status == Phase5Status.PASS
    assert builder_calls == 1
    assert repair_corrections == ["Replace generic visual with the orbital clinical mark"]
    assert result.artifact is not None
    assert result.artifact.version == "artifact_v2"
    assert result.receipt.stale_evidence == ("verification-v1", "critique-v1")


def test_runner_stops_on_second_material_gap_and_never_loops(tmp_path) -> None:
    task = make_task(tmp_path)
    calls = 0

    def builder(_task, attempt):
        nonlocal calls
        calls += 1
        return _response(task, f"INV-P5-{attempt}")

    def repair_builder(_task, attempt, _correction):
        return _response(task, f"INV-P5-REPAIR-{attempt}")

    def critic(packet):
        return _critique(
            packet,
            verdict="FAIL",
            overall_score=60,
            findings=[
                {
                    "id": "V-001",
                    "location": "Hero",
                    "expected": "Product-specific visual language",
                    "observed": "Generic hero",
                    "severity": "HIGH",
                    "evidence": "artifact",
                    "status": "OPEN",
                }
            ],
        )

    result = CompositionRunner().run(
        task,
        builder=builder,
        repair_builder=repair_builder,
        critic=critic,
        verifier=_verifier,
    )
    assert calls == 1
    assert result.status in {Phase5Status.FAIL, Phase5Status.PASS_WITH_LIMITATIONS}
    assert result.receipt.repair_invocations == 1


def test_blocked_builder_does_not_materialize_or_call_critic(tmp_path) -> None:
    task = make_task(tmp_path)

    def builder(_task, _attempt):
        return BuilderResponse(
            status=Phase5Status.BLOCKED,
            invocation_id="INV-P5-BLOCKED",
            final_message=None,
            host_invoked=False,
            load_observation="UNAVAILABLE",
            error_code="CAPABILITY_NOT_ELIGIBLE",
        )

    result = run_bounded_composition(task, builder=builder, critic=lambda _: {"verdict": "PASS"})
    assert result.status == Phase5Status.BLOCKED
    assert result.artifact is None
    assert result.receipt.critic_invocations == 0


def test_runner_rejects_object_critic_without_exact_independence(tmp_path) -> None:
    task = make_task(tmp_path)

    def builder(_task, _attempt):
        return _response(task)

    def critic(packet):
        return VisualCritique(
            benchmark_id=packet.benchmark_id,
            run_id=packet.run_id,
            inspection_id="INS-P5-NOT-INDEPENDENT",
            artifact_digest=packet.artifact.digest,
            independence="DELEGATED",
            blinded=True,
            builder_rationale_withheld=True,
            self_score_withheld=True,
            packet_digest=packet.packet_digest,
            verdict=Phase5Status.PASS,
            overall_score=90,
            evidence_confidence="HIGH",
            dimension_scores={},
            findings=(),
            top_corrections=(),
            evidence_missing=(),
        )

    with pytest.raises(ValueError):
        CompositionRunner().run(task, builder=builder, critic=critic, verifier=_verifier)
