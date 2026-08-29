"""Fixed, finite composition orchestration for the Phase 5 pilot."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Event
from typing import Protocol, cast

from .phase4_host import CapabilityInvocationAdapter
from .phase4_models import (
    CapabilityInvocationRequest,
    HostInvocationResult,
    InvocationResultStatus,
    Phase4Budget,
)
from .phase5_artifacts import (
    ArtifactCaptureError,
    extract_response_artifact,
    materialize_response_artifact,
)
from .phase5_models import (
    FIXED_GRAPH,
    ArtifactPacket,
    AssuranceReport,
    BlindPacket,
    CapabilityFingerprint,
    CompositionReceipt,
    FindingSeverity,
    Phase5Budget,
    Phase5Role,
    Phase5Status,
    Phase5Task,
    RenderRecord,
    RepairPlan,
    StructuralVerification,
    VisualCritique,
)
from .phase5_policy import (
    build_builder_request,
)
from .phase5_verification import make_blind_packet, parse_blind_critique


@dataclass(frozen=True, slots=True)
class BuilderResponse:
    status: Phase5Status
    invocation_id: str
    final_message: str | None
    host_invoked: bool
    load_observation: str
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, Phase5Status):
            raise ValueError("builder response status is invalid")
        if not self.invocation_id or "\x00" in self.invocation_id:
            raise ValueError("builder response invocation is invalid")
        if self.final_message is not None and (
            not self.final_message or "\x00" in self.final_message
        ):
            raise ValueError("builder response message is invalid")
        if not isinstance(self.host_invoked, bool):
            raise ValueError("builder host_invoked is invalid")
        if not isinstance(self.load_observation, str) or not self.load_observation:
            raise ValueError("builder load observation is invalid")
        if self.error_code is not None and (not self.error_code or "\x00" in self.error_code):
            raise ValueError("builder error code is invalid")


class CriticCallable(Protocol):
    def __call__(self, packet: BlindPacket) -> VisualCritique | Mapping[str, object]: ...


class BuilderCallable(Protocol):
    def __call__(self, task: Phase5Task, attempt: int) -> BuilderResponse: ...


class RepairBuilderCallable(Protocol):
    def __call__(self, task: Phase5Task, attempt: int, correction: str) -> BuilderResponse: ...


class VerificationCallable(Protocol):
    def __call__(
        self, task: Phase5Task, artifact: ArtifactPacket, *, version: str
    ) -> StructuralVerification: ...


@dataclass(frozen=True, slots=True)
class CompositionResult:
    status: Phase5Status
    artifact: ArtifactPacket | None
    structural: StructuralVerification | None
    critique: VisualCritique | None
    final_verification: StructuralVerification | None
    assurance: AssuranceReport
    receipt: CompositionReceipt
    repair_plan: RepairPlan | None


def _phase4_budget(budget: Phase5Budget) -> Phase4Budget:
    return Phase4Budget(
        timeout_seconds=120,
        max_context_bytes=budget.max_context_bytes,
        # The design-director can emit many bounded reasoning deltas before its
        # final response; keep the host finite without truncating normal runs.
        max_host_events=4_096,
        max_tool_calls=0,
        max_repair_iterations=0,
        max_verification_iterations=budget.max_structural_verifications,
        max_artifacts=1,
        max_evidence=budget.max_evidence_records,
        max_output_bytes=budget.max_artifact_bytes,
    )


def invoke_host_builder(
    adapter: CapabilityInvocationAdapter,
    request: CapabilityInvocationRequest,
    *,
    budget: Phase5Budget,
) -> BuilderResponse:
    """Invoke the official host and preserve its observed status verbatim."""

    try:
        preparation = adapter.prepare_invocation(request)
        errors = adapter.validate_invocation(request)
    except Exception:
        return BuilderResponse(
            Phase5Status.BLOCKED,
            request.invocation_id,
            None,
            False,
            "UNAVAILABLE",
            "HOST_PREPARATION_FAILURE",
        )
    if not preparation.supported or errors:
        return BuilderResponse(
            Phase5Status.BLOCKED,
            request.invocation_id,
            None,
            False,
            "UNAVAILABLE",
            errors[0] if errors else "HOST_INVOCATION_UNSUPPORTED",
        )
    try:
        result = adapter.request_invocation(
            request,
            budget=_phase4_budget(budget),
            cancel_event=Event(),
        )
    except Exception:
        return BuilderResponse(
            Phase5Status.FAIL,
            request.invocation_id,
            None,
            False,
            "UNKNOWN",
            "HOST_ADAPTER_FAILURE",
        )
    return _builder_response_from_host(result)


def _builder_response_from_host(result: HostInvocationResult) -> BuilderResponse:
    if result.status in {InvocationResultStatus.SUCCESS, InvocationResultStatus.PARTIAL}:
        status = Phase5Status.PASS if result.final_message else Phase5Status.FAIL
    elif result.status is InvocationResultStatus.BLOCKED:
        status = Phase5Status.BLOCKED
    else:
        status = Phase5Status.FAIL
    return BuilderResponse(
        status=status,
        invocation_id=result.turn_id or "INV-P5-HOST-UNKNOWN",
        final_message=result.final_message,
        host_invoked=result.invocation_observed,
        load_observation=result.load_observation.value,
        error_code=result.error_code,
    )


def make_host_builder(
    adapter: CapabilityInvocationAdapter,
    task: Phase5Task,
    fingerprint: CapabilityFingerprint,
    *,
    host_executable_digest: str,
    host_interpreter_digest: str,
    budget: Phase5Budget | None = None,
) -> BuilderCallable:
    selected_budget = budget or Phase5Budget()

    def builder(_task: Phase5Task, attempt: int) -> BuilderResponse:
        request = build_builder_request(
            task,
            fingerprint,
            host_executable_digest=host_executable_digest,
            host_interpreter_digest=host_interpreter_digest,
            attempt=attempt,
            budget=selected_budget,
        )
        response = invoke_host_builder(adapter, request, budget=selected_budget)
        if response.invocation_id == request.invocation_id:
            return response
        return BuilderResponse(
            response.status,
            request.invocation_id,
            response.final_message,
            response.host_invoked,
            response.load_observation,
            response.error_code,
        )

    return cast(BuilderCallable, builder)


def _normalize_critic(
    raw: VisualCritique | Mapping[str, object], packet: BlindPacket, inspection_number: int
) -> VisualCritique:
    if isinstance(raw, VisualCritique):
        if (
            raw.artifact_digest != packet.artifact.digest
            or not raw.is_independent
            or not raw.blinded
            or not raw.builder_rationale_withheld
            or not raw.self_score_withheld
            or raw.packet_digest != packet.packet_digest
        ):
            raise ValueError("critic artifact digest does not match current packet")
        return raw
    if not isinstance(raw, Mapping):
        raise ValueError("critic output is not a mapping")
    payload = dict(raw)
    required_fields = (
        "benchmark_id",
        "run_id",
        "inspection_id",
        "artifact_digest",
        "packet_digest",
        "independence",
        "blinded",
        "builder_rationale_withheld",
        "self_score_withheld",
    )
    if any(name not in payload for name in required_fields):
        raise ValueError("critic output is missing a bound blind-packet field")
    if payload["benchmark_id"] != packet.benchmark_id or payload["run_id"] != packet.run_id:
        raise ValueError("critic output is bound to a different task packet")
    if payload["artifact_digest"] != packet.artifact.digest:
        raise ValueError("critic output is bound to a different artifact")
    payload.setdefault("evidence_confidence", "MEDIUM")
    payload.setdefault("dimension_scores", {})
    payload.setdefault("findings", [])
    payload.setdefault("top_corrections", [])
    payload.setdefault("evidence_missing", [])
    critique = parse_blind_critique(
        payload,
        packet_digest=packet.packet_digest,
        require_packet_digest=True,
    )
    if not critique.is_independent:
        raise ValueError("critic output is not independent")
    return critique


def _needs_repair(critique: VisualCritique) -> bool:
    if critique.verdict is Phase5Status.BLOCKED:
        return False
    return any(
        item.status == "OPEN"
        and item.severity
        in {FindingSeverity.CRITICAL, FindingSeverity.HIGH, FindingSeverity.MEDIUM}
        for item in critique.findings
    )


def _result_status(
    critique: VisualCritique | None,
    structural: StructuralVerification | None,
    *,
    artifact: ArtifactPacket | None,
) -> Phase5Status:
    if artifact is None or critique is None:
        return Phase5Status.BLOCKED
    if structural is not None and structural.status in {Phase5Status.FAIL, Phase5Status.BLOCKED}:
        return structural.status
    if critique.verdict is Phase5Status.PASS:
        return Phase5Status.PASS
    if critique.verdict is Phase5Status.PASS_WITH_LIMITATIONS:
        return Phase5Status.PASS_WITH_LIMITATIONS
    return critique.verdict


class CompositionRunner:
    """Run only the fixed Phase 5 graph with finite builder/repair budgets."""

    def __init__(self, *, budget: Phase5Budget | None = None) -> None:
        self.budget = budget or Phase5Budget()

    def run(
        self,
        task: Phase5Task,
        *,
        builder: BuilderCallable,
        repair_builder: RepairBuilderCallable | None = None,
        critic: CriticCallable,
        verifier: VerificationCallable | None = None,
        renders: tuple[RenderRecord, ...] = (),
    ) -> CompositionResult:
        events: list[str] = ["DESIGN_BUILDER"]
        artifact_versions: list[str] = []
        stale_evidence: list[str] = []
        builder_invocations = 0
        verifier_invocations = 0
        critic_invocations = 0
        repair_invocations = 0
        repair_plan: RepairPlan | None = None
        artifact: ArtifactPacket | None = None
        structural: StructuralVerification | None = None
        final_verification: StructuralVerification | None = None
        critique: VisualCritique | None = None

        response: BuilderResponse | None = None
        extracted = None
        while builder_invocations < self.budget.max_builder_invocations:
            attempt = builder_invocations + 1
            response = builder(task, attempt)
            builder_invocations += 1
            if response.status is not Phase5Status.PASS or response.final_message is None:
                break
            try:
                extracted = extract_response_artifact(
                    response.final_message, max_bytes=self.budget.max_artifact_bytes
                )
                break
            except ArtifactCaptureError:
                if builder_invocations >= self.budget.max_builder_invocations:
                    response = BuilderResponse(
                        Phase5Status.FAIL,
                        response.invocation_id,
                        None,
                        response.host_invoked,
                        response.load_observation,
                        "ARTIFACT_RESPONSE_INVALID",
                    )
                    break
        if extracted is not None and response is not None:
            try:
                artifact = materialize_response_artifact(
                    extracted,
                    task,
                    version="artifact_v1",
                    artifact_id="ART-P5-V1",
                    invocation_id=response.invocation_id,
                )
                artifact_versions.append(artifact.version)
            except (ArtifactCaptureError, ValueError):
                artifact = None
        if artifact is None:
            events.append("ASSURANCE")
            receipt = CompositionReceipt(
                task.task_id,
                task.run_id,
                Phase5Status.BLOCKED,
                FIXED_GRAPH,
                tuple(events),
                builder_invocations,
                0,
                0,
                0,
                tuple(artifact_versions),
                tuple(stale_evidence),
                "BLOCKED:EXTERNAL_VERIFIER_NOT_ELIGIBLE",
            )
            assurance = AssuranceReport(
                task.run_id,
                Phase5Status.BLOCKED,
                "NONE",
                "The builder did not produce a safe response-derived artifact",
                ("REAL_ARTIFACT_REQUIRED",),
                (
                    response.error_code
                    if response and response.error_code
                    else "BUILDER_UNAVAILABLE",
                ),
                None,
                None,
                None,
                int(time.time()),
            )
            return CompositionResult(
                Phase5Status.BLOCKED,
                None,
                None,
                None,
                None,
                assurance,
                receipt,
                None,
            )

        if verifier is None:
            events.append("ASSURANCE")
            receipt = CompositionReceipt(
                task.task_id,
                task.run_id,
                Phase5Status.BLOCKED,
                FIXED_GRAPH,
                tuple(events),
                builder_invocations,
                0,
                0,
                0,
                tuple(artifact_versions),
                tuple(stale_evidence),
                "BLOCKED:EXTERNAL_VERIFIER_NOT_ELIGIBLE",
            )
            assurance = AssuranceReport(
                task.run_id,
                Phase5Status.BLOCKED,
                "NONE",
                "A structural verifier is required before a composition can be accepted",
                ("STRUCTURAL_VERIFIER_REQUIRED",),
                (),
                artifact.digest,
                None,
                None,
                int(time.time()),
            )
            return CompositionResult(
                Phase5Status.BLOCKED,
                artifact,
                None,
                None,
                None,
                assurance,
                receipt,
                None,
            )

        events.append("STRUCTURAL_VERIFICATION")
        if verifier is not None:
            structural = verifier(task, artifact, version=artifact.version)
            verifier_invocations += 1
        events.append("VISUAL_CRITIQUE")
        packet = make_blind_packet(task, artifact, tuple(renders))
        raw_critique = critic(packet)
        critic_invocations += 1
        critique = _normalize_critic(raw_critique, packet, 1)
        repair_failed = False
        if (
            _needs_repair(critique)
            and repair_invocations < self.budget.max_repairs
            and builder_invocations < self.budget.max_builder_invocations
        ):
            events.append("OPTIONAL_REPAIR")
            repair_plan = RepairPlan(
                source_artifact_version=artifact.version,
                target_artifact_version="artifact_v2",
                owner=Phase5Role.REPAIRER,
                correction=(
                    critique.top_corrections[0]
                    if critique.top_corrections
                    else "Address the highest-severity open visual finding"
                ),
                reason="The blind critic found a material open gap and one repair budget remains",
                budget_remaining=0,
                status=Phase5Status.PASS_WITH_LIMITATIONS,
            )
            if repair_builder is None:
                repair_failed = True
            else:
                repair_response = repair_builder(
                    task, builder_invocations + 1, repair_plan.correction
                )
                builder_invocations += 1
                repair_invocations = 1
                if (
                    repair_response.status is Phase5Status.PASS
                    and repair_response.final_message is not None
                ):
                    try:
                        repair_artifact = extract_response_artifact(
                            repair_response.final_message, max_bytes=self.budget.max_artifact_bytes
                        )
                        artifact = materialize_response_artifact(
                            repair_artifact,
                            task,
                            version="artifact_v2",
                            artifact_id="ART-P5-V2",
                            invocation_id=repair_response.invocation_id,
                            parent_artifact_digest=artifact.digest,
                        )
                        artifact_versions.append(artifact.version)
                        stale_evidence.extend(("verification-v1", "critique-v1"))
                        events.append("FINAL_VERIFICATION")
                        if verifier is not None:
                            final_verification = verifier(task, artifact, version=artifact.version)
                            verifier_invocations += 1
                        packet = make_blind_packet(task, artifact, tuple(renders))
                        critique = _normalize_critic(critic(packet), packet, 2)
                        critic_invocations += 1
                    except (ArtifactCaptureError, ValueError):
                        repair_failed = True
                else:
                    repair_failed = True
        if "FINAL_VERIFICATION" not in events:
            events.append("FINAL_VERIFICATION")
            if verifier is not None and structural is not None:
                final_verification = structural
        events.append("ASSURANCE")
        status = _result_status(critique, final_verification or structural, artifact=artifact)
        if repair_failed:
            status = Phase5Status.FAIL
        limitations = ["EXTERNAL_VERIFIER_NOT_ELIGIBLE", "HOST_LOAD_UNOBSERVABLE"]
        if repair_plan is not None and final_verification is None:
            limitations.append("FINAL_BROWSER_VERIFICATION_REQUIRED")
        assurance_status = status
        if status is Phase5Status.PASS and limitations:
            assurance_status = Phase5Status.PASS_WITH_LIMITATIONS
        observed_verification = final_verification if final_verification is not None else structural
        assurance = AssuranceReport(
            task.run_id,
            assurance_status,
            "A" if artifact is not None else "NONE",
            "Bounded builder and blind critique completed; external verifier is not eligible",
            tuple(limitations),
            (),
            artifact.digest,
            observed_verification.digest if observed_verification is not None else None,
            critique.packet_digest if critique else None,
            int(time.time()),
        )
        receipt = CompositionReceipt(
            task.task_id,
            task.run_id,
            status,
            (
                "DESIGN_BUILDER",
                "STRUCTURAL_VERIFICATION",
                "VISUAL_CRITIQUE",
                "OPTIONAL_REPAIR",
                "FINAL_VERIFICATION",
                "ASSURANCE",
            ),
            tuple(events),
            builder_invocations,
            verifier_invocations,
            critic_invocations,
            repair_invocations,
            tuple(artifact_versions),
            tuple(stale_evidence),
            "BLOCKED:EXTERNAL_VERIFIER_NOT_ELIGIBLE",
        )
        return CompositionResult(
            status,
            artifact,
            structural,
            critique,
            final_verification,
            assurance,
            receipt,
            repair_plan,
        )


def run_bounded_composition(
    task: Phase5Task,
    *,
    builder: BuilderCallable,
    repair_builder: RepairBuilderCallable | None = None,
    critic: CriticCallable,
    verifier: VerificationCallable | None = None,
    renders: tuple[RenderRecord, ...] = (),
    budget: Phase5Budget | None = None,
) -> CompositionResult:
    return CompositionRunner(budget=budget).run(
        task,
        builder=builder,
        repair_builder=repair_builder,
        critic=critic,
        verifier=verifier,
        renders=renders,
    )
