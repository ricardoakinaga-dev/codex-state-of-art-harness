"""Explicit, project-local command surface for the Phase 5 composition pilot."""

from __future__ import annotations

import argparse
import json
import stat
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .phase3_host import CodexHostAdapter
from .phase3_models import CapabilityRecord
from .phase3_resolution import ResolutionEngine
from .phase4_evidence import EvidenceError, EvidenceWriter
from .phase4_host import CodexAppServerAdapter, HostBinding
from .phase4_models import CapabilityInvocationRequest
from .phase5_artifacts import (
    ArtifactCaptureError,
    extract_response_artifact,
    materialize_response_artifact,
)
from .phase5_execution import BuilderResponse, invoke_host_builder
from .phase5_finalization import (
    artifact_from_receipt as _artifact_from_receipt,
)
from .phase5_finalization import (
    finalize as _finalize,
)
from .phase5_finalization import (
    needs_repair as _needs_repair,
)
from .phase5_finalization import (
    prepare_review as _prepare_review,
)
from .phase5_finalization import validate_receipt_binding as _validate_receipt_binding
from .phase5_models import (
    FIXED_GRAPH,
    ArtifactPacket,
    BlindPacket,
    CapabilityFingerprint,
    EligibilityReport,
    Phase5Budget,
    Phase5Role,
    Phase5Status,
    Phase5Task,
    RenderRecord,
    RepairPlan,
    public_data,
)
from .phase5_paths import (
    Phase5CliError,
)
from .phase5_paths import (
    evidence_path as _evidence_path,
)
from .phase5_paths import (
    policy_path as _policy_path,
)
from .phase5_paths import (
    resolved_project_root as _resolved_project_root,
)
from .phase5_paths import (
    task_path as _task_path,
)
from .phase5_pilot import (
    Phase5PilotInputError,
    load_task,
    public_task,
    read_json_mapping,
    write_public_json,
)
from .phase5_policy import (
    Phase5Allowlist,
    build_builder_request,
    build_fingerprint,
    evaluate_eligibility,
    validate_fixed_graph,
)
from .phase5_verification import make_blind_packet, parse_blind_critique


class Phase5AppServerAdapter(CodexAppServerAdapter):
    """Keep Phase 5's exact package path usable in the isolated host runtime."""

    @staticmethod
    def _skill_is_discovered(
        response: Mapping[str, object], request: CapabilityInvocationRequest
    ) -> bool:
        if CodexAppServerAdapter._skill_is_discovered(response, request):
            return True
        candidate = Path(request.skill_path)
        try:
            metadata = candidate.lstat()
        except OSError:
            return False
        return candidate.is_file() and not candidate.is_symlink() and stat.S_ISREG(metadata.st_mode)


@dataclass(frozen=True, slots=True)
class PilotPreflight:
    task: Phase5Task
    allowlist: Phase5Allowlist
    adapter: CodexHostAdapter
    host_adapter: Phase5AppServerAdapter
    selected_record: CapabilityRecord | None
    fingerprint: CapabilityFingerprint | None
    eligibility: EligibilityReport | None
    secondary: dict[str, object]
    resolution_status: str
    resolution_blockers: tuple[str, ...]
    binding: HostBinding | None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness-phase5",
        description="Run the bounded Phase 5 design-director composition pilot.",
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    pilot = commands.add_parser("pilot", help="preflight and optionally run the real builder")
    pilot.add_argument("--task", type=Path)
    pilot.add_argument("--policy", type=Path)
    pilot.add_argument("--evidence-dir", type=Path)
    pilot.add_argument("--controlled-real", action="store_true")
    pilot.add_argument("--confirm-fingerprint")
    pilot.add_argument("--json", action="store_true", dest="json_output")
    finalize = commands.add_parser(
        "finalize", help="bind browser renders and a blind critic packet to the artifact"
    )
    finalize.add_argument("--task", type=Path)
    finalize.add_argument("--evidence-dir", type=Path)
    finalize.add_argument("--desktop", type=Path, required=True)
    finalize.add_argument("--mobile", type=Path, required=True)
    finalize.add_argument("--critique", type=Path, required=True)
    finalize.add_argument(
        "--artifact-version", choices=("artifact_v1", "artifact_v2"), default="artifact_v1"
    )
    finalize.add_argument("--console-errors", type=Path)
    finalize.add_argument("--network-failures", type=Path)
    finalize.add_argument("--json", action="store_true", dest="json_output")
    review = commands.add_parser(
        "prepare-review", help="prepare the exact blind packet for an independent critic"
    )
    review.add_argument("--task", type=Path)
    review.add_argument("--evidence-dir", type=Path)
    review.add_argument("--desktop", type=Path, required=True)
    review.add_argument("--mobile", type=Path, required=True)
    review.add_argument(
        "--artifact-version", choices=("artifact_v1", "artifact_v2"), default="artifact_v1"
    )
    review.add_argument("--json", action="store_true", dest="json_output")
    repair = commands.add_parser(
        "repair", help="run one bounded response-only repair from an accepted blind finding"
    )
    repair.add_argument("--task", type=Path)
    repair.add_argument("--policy", type=Path)
    repair.add_argument("--evidence-dir", type=Path)
    repair.add_argument("--confirm-fingerprint", required=True)
    repair.add_argument("--correction", required=True)
    repair.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _record_summary(record: CapabilityRecord | None) -> dict[str, object] | None:
    if record is None:
        return None
    return {
        "capability_id": record.capability_id,
        "version": record.version,
        "scope": record.scope.value,
        "canonical_path": record.path,
        "package_fingerprint": record.content_hash,
        "manifest_fingerprint": build_fingerprint(record).manifest_fingerprint,
        "status": record.status.value,
        "load_eligibility": record.load_eligibility,
        "trust": record.trust.level.value,
        "compatibility": record.compatibility.status.value,
        "root_id": record.root_id,
    }


def _secondary_summary(
    record: CapabilityRecord | None,
    fingerprint: CapabilityFingerprint | None,
    allowlist: Phase5Allowlist,
) -> dict[str, object]:
    if record is None or fingerprint is None:
        return {
            "capability_id": "verification-loop",
            "status": Phase5Status.BLOCKED.value,
            "blocker": "EXTERNAL_VERIFIER_NOT_ELIGIBLE",
            "observed": False,
        }
    report = evaluate_eligibility(
        fingerprint,
        allowlist,
        Phase5Role.VISUAL_CRITIC,
    )
    return cast(dict[str, object], public_data(report))


def _preflight(root: Path, task: Phase5Task, policy_path: Path) -> PilotPreflight:
    allowlist = Phase5Allowlist.from_json(policy_path)
    adapter = CodexHostAdapter(
        project_root=root,
        workspace_root=Path(task.workspace),
        home_dir=Path.home(),
    )
    inventory = adapter.discover_capabilities()
    resolution = ResolutionEngine().resolve(inventory, "design-director")
    selected = resolution.selected[0] if len(resolution.selected) == 1 else None
    fingerprint = build_fingerprint(selected) if selected is not None else None
    eligibility = (
        evaluate_eligibility(fingerprint, allowlist, Phase5Role.DESIGN_BUILDER)
        if fingerprint is not None
        else None
    )
    secondary_record = next(
        (item for item in inventory.capabilities if item.capability_id == "verification-loop"),
        None,
    )
    secondary_fingerprint = (
        build_fingerprint(secondary_record) if secondary_record is not None else None
    )
    host_adapter = Phase5AppServerAdapter()
    binding = host_adapter._resolved_host_binding()
    return PilotPreflight(
        task=task,
        allowlist=allowlist,
        adapter=adapter,
        host_adapter=host_adapter,
        selected_record=selected,
        fingerprint=fingerprint,
        eligibility=eligibility,
        secondary=_secondary_summary(secondary_record, secondary_fingerprint, allowlist),
        resolution_status=resolution.status.value,
        resolution_blockers=resolution.blockers,
        binding=binding,
    )


def _preflight_route(
    preflight: PilotPreflight,
    *,
    controlled_real: bool,
    confirmed_fingerprint: str | None,
) -> dict[str, object]:
    validate_fixed_graph(FIXED_GRAPH)
    blockers: list[str] = list(preflight.resolution_blockers)
    if preflight.selected_record is None:
        blockers.append("CAPABILITY_NOT_RESOLVED_EXACTLY")
    if preflight.eligibility is None:
        blockers.append("BUILDER_ELIGIBILITY_UNAVAILABLE")
    elif preflight.eligibility.status is not Phase5Status.PASS:
        blockers.extend(preflight.eligibility.blockers)
    if not controlled_real:
        blockers.append("REAL_MODE_CONFIRMATION_REQUIRED")
    elif preflight.fingerprint is not None:
        if confirmed_fingerprint != preflight.fingerprint.package_fingerprint:
            blockers.append(
                "FINGERPRINT_CONFIRMATION_REQUIRED"
                if confirmed_fingerprint is None
                else "FINGERPRINT_CONFIRMATION_MISMATCH"
            )
        if preflight.binding is None:
            blockers.append("HOST_EXECUTABLE_UNAVAILABLE")
        elif preflight.binding[5] is None:
            blockers.append("HOST_INTERPRETER_UNAVAILABLE")
    status = Phase5Status.PASS if not blockers else Phase5Status.BLOCKED
    return {
        "schema_version": "P5-ROUTE-1",
        "task_id": preflight.task.task_id,
        "run_id": preflight.task.run_id,
        "status": status,
        "requested_mode": "CONTROLLED_REAL" if controlled_real else "PREPARE_ONLY",
        "route": "DESIGN_DIRECTOR_RESPONSE_ONLY" if status is Phase5Status.PASS else "BLOCKED",
        "selected": _record_summary(preflight.selected_record),
        "builder_eligibility": public_data(preflight.eligibility),
        "secondary": preflight.secondary,
        "resolution_status": preflight.resolution_status,
        "resolution_blockers": preflight.resolution_blockers,
        "blockers": tuple(dict.fromkeys(blockers)),
        "graph": FIXED_GRAPH,
        "tools": "DENY",
        "scripts": "DENY_METADATA_ONLY",
        "shell": "DENY",
        "network": "DENY",
        "mcp": "DENY",
        "providers": "DENY",
        "credentials": "DENY",
    }


def _write_preflight(
    writer: EvidenceWriter,
    preflight: PilotPreflight,
    route: dict[str, object],
    request: CapabilityInvocationRequest | None,
) -> None:
    write_public_json(writer, "task.json", public_task(preflight.task))
    write_public_json(writer, "acceptance-criteria.json", preflight.task.criteria)
    write_public_json(writer, "eligibility.json", preflight.eligibility or route)
    write_public_json(writer, "route-decision.json", route)
    if request is not None:
        write_public_json(writer, "builder-context-manifest.json", request.context)
        write_public_json(writer, "builder-authorization.json", request.authorization)
    else:
        write_public_json(
            writer,
            "builder-context-manifest.json",
            {"status": Phase5Status.NOT_RUN, "reason": "builder request was blocked"},
        )
        write_public_json(
            writer,
            "builder-authorization.json",
            {"status": Phase5Status.NOT_RUN, "reason": "builder request was blocked"},
        )


def _request_for_attempt(
    preflight: PilotPreflight, attempt: int, budget: Phase5Budget
) -> CapabilityInvocationRequest:
    if preflight.fingerprint is None or preflight.binding is None:
        raise Phase5CliError("exact builder or host binding is unavailable")
    if preflight.binding[5] is None:
        raise Phase5CliError("host interpreter fingerprint is unavailable")
    return build_builder_request(
        preflight.task,
        preflight.fingerprint,
        host_executable_digest=preflight.binding[2],
        host_interpreter_digest=preflight.binding[5],
        attempt=attempt,
        budget=budget,
    )


def _builder_receipt(
    task: Phase5Task,
    responses: list[BuilderResponse],
    requests: list[CapabilityInvocationRequest],
    artifact: ArtifactPacket | None,
    fingerprint: CapabilityFingerprint,
) -> dict[str, object]:
    attempts = []
    for response, request in zip(responses, requests, strict=False):
        invocation_id = request.invocation_id
        attempts.append(
            {
                "invocation_id": invocation_id,
                "status": response.status,
                "host_invoked": response.host_invoked,
                "load_observation": response.load_observation,
                "error_code": response.error_code,
                "authorization_id": request.authorization.authorization_id,
                "context_digest": request.context.digest,
            }
        )
    last = responses[-1] if responses else None
    last_request = requests[-1] if requests else None
    return {
        "schema_version": "P5-BUILDER-RECEIPT-1",
        "task_id": task.task_id,
        "run_id": task.run_id,
        "status": last.status if last is not None else Phase5Status.BLOCKED,
        "attempt_count": len(responses),
        "attempts": attempts,
        "artifact_id": artifact.artifact_id if artifact is not None else None,
        "artifact_version": artifact.version if artifact is not None else None,
        "artifact_path": artifact.path if artifact is not None else None,
        "artifact_digest": artifact.digest if artifact is not None else None,
        "artifact_size_bytes": artifact.size_bytes if artifact is not None else None,
        "producer_capability": "design-director",
        "capability_id": fingerprint.capability_id,
        "capability_version": fingerprint.version,
        "package_fingerprint": fingerprint.package_fingerprint,
        "manifest_fingerprint": fingerprint.manifest_fingerprint,
        "authorization_id": (
            last_request.authorization.authorization_id if last_request is not None else None
        ),
        "context_digest": last_request.context.digest if last_request is not None else None,
        "rationale_withheld_from_critic": True,
        "created_at": int(time.time()),
    }


def _run_builder(
    preflight: PilotPreflight,
    writer: EvidenceWriter,
) -> dict[str, object]:
    if preflight.fingerprint is None:
        raise Phase5CliError("builder fingerprint is unavailable")
    budget = Phase5Budget()
    requests: list[CapabilityInvocationRequest] = []
    responses: list[BuilderResponse] = []
    extracted = None
    for attempt in range(1, budget.max_builder_invocations + 1):
        request = _request_for_attempt(preflight, attempt, budget)
        requests.append(request)
        response = invoke_host_builder(preflight.host_adapter, request, budget=budget)
        responses.append(response)
        if response.status is not Phase5Status.PASS or response.final_message is None:
            break
        try:
            extracted = extract_response_artifact(
                response.final_message, max_bytes=budget.max_artifact_bytes
            )
            break
        except ArtifactCaptureError:
            if attempt == budget.max_builder_invocations:
                break
    request_for_evidence = requests[-1] if requests else None
    route = {
        "schema_version": "P5-ROUTE-1",
        "task_id": preflight.task.task_id,
        "run_id": preflight.task.run_id,
        "status": Phase5Status.PASS,
        "requested_mode": "CONTROLLED_REAL",
        "route": "DESIGN_DIRECTOR_RESPONSE_ONLY",
        "selected": _record_summary(preflight.selected_record),
        "builder_eligibility": public_data(preflight.eligibility),
        "secondary": preflight.secondary,
        "resolution_status": preflight.resolution_status,
        "resolution_blockers": preflight.resolution_blockers,
        "blockers": (),
        "graph": FIXED_GRAPH,
        "tools": "DENY",
        "scripts": "DENY_METADATA_ONLY",
        "shell": "DENY",
        "network": "DENY",
        "mcp": "DENY",
        "providers": "DENY",
        "credentials": "DENY",
    }
    _write_preflight(writer, preflight, route, request_for_evidence)
    artifact: ArtifactPacket | None = None
    if extracted is not None and responses:
        try:
            artifact = materialize_response_artifact(
                extracted,
                preflight.task,
                version="artifact_v1",
                artifact_id="ART-P5-V1",
                invocation_id=responses[-1].invocation_id,
            )
            writer.write_text(
                "artifact-v1/index.html", Path(artifact.path).read_text(encoding="utf-8")
            )
            write_public_json(writer, "artifact-v1/packet.json", artifact)
        except (ArtifactCaptureError, OSError, UnicodeError, ValueError):
            artifact = None
    receipt = _builder_receipt(
        preflight.task,
        responses,
        requests,
        artifact,
        preflight.fingerprint,
    )
    write_public_json(writer, "builder-invocation-receipt.json", receipt)
    if artifact is None:
        return {
            "schema_version": "P5-PILOT-1",
            "status": Phase5Status.BLOCKED,
            "next_stage": "NONE",
            "builder_receipt": receipt,
        }
    return {
        "schema_version": "P5-PILOT-1",
        "status": Phase5Status.PASS_WITH_LIMITATIONS,
        "next_stage": "NATIVE_BROWSER_RENDER_AND_BLIND_CRITIQUE",
        "artifact": public_data(artifact),
        "builder_receipt": receipt,
        "limitations": ("STRUCTURAL_AND_VISUAL_FINALIZATION_PENDING",),
    }


def _repair_attempt_record(
    response: BuilderResponse, request: CapabilityInvocationRequest
) -> dict[str, object]:
    return {
        "invocation_id": request.invocation_id,
        "response_invocation_id": response.invocation_id,
        "status": response.status,
        "host_invoked": response.host_invoked,
        "load_observation": response.load_observation,
        "error_code": response.error_code,
    }


def _bound_packet_from_evidence(
    task: Phase5Task,
    artifact: ArtifactPacket,
    packet_raw: Mapping[str, object],
    evidence_root: Path,
) -> BlindPacket:
    if packet_raw.get("benchmark_id") != "P5-DESIGN-1" or packet_raw.get("run_id") != task.run_id:
        raise Phase5CliError("artifact_v1 blind packet task identity is invalid")
    raw_artifact = packet_raw.get("artifact")
    if not isinstance(raw_artifact, Mapping) or raw_artifact.get("digest") != artifact.digest:
        raise Phase5CliError("artifact_v1 blind packet artifact is not bound")
    raw_renders = packet_raw.get("renders")
    if not isinstance(raw_renders, list) or not raw_renders:
        raise Phase5CliError("artifact_v1 blind packet has no renders")
    renders: list[RenderRecord] = []
    for raw_render in raw_renders:
        if not isinstance(raw_render, Mapping):
            raise Phase5CliError("artifact_v1 blind packet render is invalid")
        render_id = raw_render.get("render_id")
        path = raw_render.get("path")
        version = raw_render.get("artifact_version")
        viewport = raw_render.get("viewport")
        if isinstance(viewport, list) and len(viewport) == 2:
            width, height = viewport
        else:
            width, height = None, None
        if (
            not isinstance(render_id, str)
            or not isinstance(path, str)
            or not isinstance(version, str)
            or version != artifact.version
            or not isinstance(width, int)
            or isinstance(width, bool)
            or not isinstance(height, int)
            or isinstance(height, bool)
        ):
            raise Phase5CliError("artifact_v1 blind packet render binding is invalid")
        try:
            render = RenderRecord.from_file(
                render_id,
                version,
                path,
                (width, height),
                root=evidence_root,
                captured_at=0,
            )
        except ValueError as exc:
            raise Phase5CliError("artifact_v1 blind packet render cannot be revalidated") from exc
        if raw_render.get("digest") != render.digest:
            raise Phase5CliError("artifact_v1 blind packet render is stale")
        renders.append(render)
    packet = make_blind_packet(
        task,
        artifact,
        tuple(renders),
        benchmark_id=str(packet_raw["benchmark_id"]),
    )
    if packet_raw.get("packet_digest") != packet.packet_digest:
        raise Phase5CliError("artifact_v1 blind packet digest is stale")
    return packet


def _repair(root: Path, arguments: argparse.Namespace) -> dict[str, object]:
    task = load_task(_task_path(root, arguments.task), project_root=root)
    policy_path = _policy_path(root, arguments.policy)
    evidence_root = _evidence_path(root, arguments.evidence_dir)
    writer = EvidenceWriter(evidence_root)
    preflight = _preflight(root, task, policy_path)
    route = _preflight_route(
        preflight,
        controlled_real=True,
        confirmed_fingerprint=arguments.confirm_fingerprint,
    )
    write_public_json(writer, "repair-route-decision.json", route)
    v1_receipt_path = evidence_root / "builder-invocation-receipt.json"
    if route["status"] is not Phase5Status.PASS:
        blocked_receipt = {
            "schema_version": "P5-REPAIR-RECEIPT-1",
            "task_id": task.task_id,
            "run_id": task.run_id,
            "status": Phase5Status.BLOCKED,
            "attempt_count": 0,
            "attempts": (),
            "artifact_id": None,
            "artifact_version": None,
            "artifact_path": None,
            "artifact_digest": None,
            "parent_artifact_digest": None,
            "rationale_withheld_from_critic": True,
            "blockers": route["blockers"],
            "created_at": int(time.time()),
        }
        write_public_json(writer, "builder-repair-receipt.json", blocked_receipt)
        return {
            "schema_version": "P5-REPAIR-1",
            "status": Phase5Status.BLOCKED,
            "next_stage": "NONE",
            "route": route,
        }
    if not v1_receipt_path.is_file():
        raise Phase5CliError("artifact_v1 builder receipt is required before repair")
    v1_receipt = cast(dict[str, object], dict(read_json_mapping(v1_receipt_path)))
    v1_attempt_count = v1_receipt.get("attempt_count")
    if not isinstance(v1_attempt_count, int) or v1_attempt_count < 1:
        raise Phase5CliError("artifact_v1 builder receipt has no successful attempt budget")
    if v1_attempt_count >= Phase5Budget().max_builder_invocations:
        raise Phase5CliError("builder invocation budget is exhausted before repair")
    v1_identity = _validate_receipt_binding(
        task,
        v1_receipt,
        eligibility=read_json_mapping(evidence_root / "eligibility.json"),
        authorization=read_json_mapping(evidence_root / "builder-authorization.json"),
        context=read_json_mapping(evidence_root / "builder-context-manifest.json"),
    )
    v1_artifact = _artifact_from_receipt(
        task,
        v1_receipt,
        version="artifact_v1",
        expected_identity=v1_identity,
    )
    packet_raw = read_json_mapping(evidence_root / "blind-packet-v1.json")
    critique_raw = read_json_mapping(evidence_root / "critique-v1.json")
    packet = _bound_packet_from_evidence(task, v1_artifact, packet_raw, evidence_root)
    packet_digest = packet.packet_digest
    if critique_raw.get("benchmark_id") != packet.benchmark_id:
        raise Phase5CliError("artifact_v1 critique benchmark is not bound to the packet")
    if critique_raw.get("run_id") != packet.run_id:
        raise Phase5CliError("artifact_v1 critique run is not bound to the packet")
    if critique_raw.get("packet_digest") != packet_digest:
        raise Phase5CliError("artifact_v1 critique packet digest is not bound")
    if critique_raw.get("artifact_digest") != v1_artifact.digest:
        raise Phase5CliError("artifact_v1 critique is not bound to the current artifact")
    critique = parse_blind_critique(
        critique_raw,
        packet_digest=packet_digest,
        require_packet_digest=True,
    )
    if not _needs_repair(critique):
        raise Phase5CliError("artifact_v1 critique does not authorize a material repair")
    correction = arguments.correction
    if not isinstance(correction, str) or not correction or "\x00" in correction:
        raise Phase5CliError("repair correction is invalid")
    if correction not in critique.top_corrections:
        raise Phase5CliError("repair correction must be copied from the blind critic handoff")
    repair_receipt_path = evidence_root / "builder-repair-receipt.json"
    if repair_receipt_path.exists():
        existing_receipt = cast(dict[str, object], dict(read_json_mapping(repair_receipt_path)))
        if existing_receipt.get("repair_correction") != correction:
            raise Phase5CliError("existing repair receipt is bound to a different correction")
        if (
            existing_receipt.get("status") != Phase5Status.PASS
            or existing_receipt.get("artifact_version") != "artifact_v2"
        ):
            raise Phase5CliError("the bounded repair has already been attempted")
        existing_identity = _validate_receipt_binding(
            task,
            existing_receipt,
            eligibility=read_json_mapping(evidence_root / "eligibility.json"),
            authorization=read_json_mapping(evidence_root / "builder-repair-authorization.json"),
            context=read_json_mapping(evidence_root / "builder-repair-context-manifest.json"),
        )
        existing_artifact = _artifact_from_receipt(
            task,
            existing_receipt,
            version="artifact_v2",
            expected_identity=existing_identity,
        )
        if existing_artifact.parent_artifact_digest != v1_artifact.digest:
            raise Phase5CliError("existing repair receipt is not chained to artifact_v1")
        repair_plan = RepairPlan(
            source_artifact_version="artifact_v1",
            target_artifact_version="artifact_v2",
            owner=Phase5Role.REPAIRER,
            correction=correction,
            reason=(
                "The blind visual critique reported a material open finding; "
                "one repair was authorized"
            ),
            budget_remaining=0,
            status=Phase5Status.PASS_WITH_LIMITATIONS,
        )
        write_public_json(writer, "repair-plan.json", repair_plan)
        return {
            "schema_version": "P5-REPAIR-1",
            "status": Phase5Status.PASS_WITH_LIMITATIONS,
            "next_stage": "NATIVE_BROWSER_RENDER_AND_BLIND_CRITIQUE_V2",
            "artifact": public_data(existing_artifact),
            "repair_plan": public_data(repair_plan),
            "repair_receipt": existing_receipt,
            "recovered": True,
        }
    if preflight.fingerprint is None or preflight.binding is None or preflight.binding[5] is None:
        raise Phase5CliError("exact builder or host binding is unavailable for repair")
    request = build_builder_request(
        task,
        preflight.fingerprint,
        host_executable_digest=preflight.binding[2],
        host_interpreter_digest=preflight.binding[5],
        attempt=v1_attempt_count + 1,
        budget=Phase5Budget(),
        repair_instruction=correction,
    )
    write_public_json(writer, "builder-repair-context-manifest.json", request.context)
    write_public_json(writer, "builder-repair-authorization.json", request.authorization)
    response = invoke_host_builder(preflight.host_adapter, request, budget=Phase5Budget())
    attempt = _repair_attempt_record(response, request)
    artifact: ArtifactPacket | None = None
    error_code = response.error_code
    if response.status is Phase5Status.PASS and response.final_message is not None:
        try:
            extracted = extract_response_artifact(
                response.final_message,
                max_bytes=Phase5Budget().max_artifact_bytes,
            )
            artifact = materialize_response_artifact(
                extracted,
                task,
                version="artifact_v2",
                artifact_id="ART-P5-V2",
                invocation_id=response.invocation_id,
                parent_artifact_digest=v1_artifact.digest,
            )
            writer.write_text(
                "artifact-v2/index.html",
                Path(artifact.path).read_text(encoding="utf-8"),
            )
            write_public_json(writer, "artifact-v2/packet.json", artifact)
        except (ArtifactCaptureError, OSError, UnicodeError, ValueError):
            error_code = "ARTIFACT_RESPONSE_INVALID"
    receipt = {
        "schema_version": "P5-REPAIR-RECEIPT-1",
        "task_id": task.task_id,
        "run_id": task.run_id,
        "status": response.status if artifact is not None else Phase5Status.FAIL,
        "attempt_count": 1,
        "attempts": (attempt,),
        "artifact_id": artifact.artifact_id if artifact is not None else None,
        "artifact_version": artifact.version if artifact is not None else None,
        "artifact_path": artifact.path if artifact is not None else None,
        "artifact_digest": artifact.digest if artifact is not None else None,
        "artifact_size_bytes": artifact.size_bytes if artifact is not None else None,
        "parent_artifact_digest": v1_artifact.digest,
        "producer_capability": "design-director",
        "capability_id": preflight.fingerprint.capability_id,
        "capability_version": preflight.fingerprint.version,
        "package_fingerprint": preflight.fingerprint.package_fingerprint,
        "manifest_fingerprint": preflight.fingerprint.manifest_fingerprint,
        "authorization_id": request.authorization.authorization_id,
        "context_digest": request.context.digest,
        "repair_correction": correction,
        "error_code": error_code,
        "rationale_withheld_from_critic": True,
        "created_at": int(time.time()),
    }
    write_public_json(writer, "builder-repair-receipt.json", receipt)
    if artifact is None:
        return {
            "schema_version": "P5-REPAIR-1",
            "status": Phase5Status.FAIL,
            "next_stage": "NONE",
            "repair_receipt": receipt,
        }
    repair_plan = RepairPlan(
        source_artifact_version="artifact_v1",
        target_artifact_version="artifact_v2",
        owner=Phase5Role.REPAIRER,
        correction=correction,
        reason=(
            "The blind visual critique reported a material open finding; one repair was authorized"
        ),
        budget_remaining=0,
        status=Phase5Status.PASS_WITH_LIMITATIONS,
    )
    write_public_json(writer, "repair-plan.json", repair_plan)
    return {
        "schema_version": "P5-REPAIR-1",
        "status": Phase5Status.PASS_WITH_LIMITATIONS,
        "next_stage": "NATIVE_BROWSER_RENDER_AND_BLIND_CRITIQUE_V2",
        "artifact": public_data(artifact),
        "repair_plan": public_data(repair_plan),
        "repair_receipt": receipt,
    }


def _pilot(root: Path, arguments: argparse.Namespace) -> dict[str, object]:
    task = load_task(_task_path(root, arguments.task), project_root=root)
    policy_path = _policy_path(root, arguments.policy)
    evidence_root = _evidence_path(root, arguments.evidence_dir)
    writer = EvidenceWriter(evidence_root)
    preflight = _preflight(root, task, policy_path)
    route = _preflight_route(
        preflight,
        controlled_real=arguments.controlled_real,
        confirmed_fingerprint=arguments.confirm_fingerprint,
    )
    request = None
    if route["status"] == Phase5Status.PASS:
        request = _request_for_attempt(preflight, 1, Phase5Budget())
        result = _run_builder(preflight, writer)
        result["route"] = route
        return result
    _write_preflight(writer, preflight, route, request)
    write_public_json(
        writer,
        "builder-invocation-receipt.json",
        {
            "schema_version": "P5-BUILDER-RECEIPT-1",
            "task_id": task.task_id,
            "run_id": task.run_id,
            "status": Phase5Status.BLOCKED,
            "attempt_count": 0,
            "attempts": (),
            "artifact_id": None,
            "artifact_version": None,
            "artifact_path": None,
            "artifact_digest": None,
            "rationale_withheld_from_critic": True,
            "created_at": int(time.time()),
        },
    )
    return {
        "schema_version": "P5-PILOT-1",
        "status": Phase5Status.BLOCKED,
        "next_stage": "NONE",
        "route": route,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        root = _resolved_project_root(arguments.project_root)
        if arguments.command == "pilot":
            payload = _pilot(root, arguments)
        elif arguments.command == "finalize":
            payload = _finalize(root, arguments)
        elif arguments.command == "prepare-review":
            payload = _prepare_review(root, arguments)
        elif arguments.command == "repair":
            payload = _repair(root, arguments)
        else:
            raise Phase5CliError("unsupported Phase 5 command")
    except (
        ArtifactCaptureError,
        EvidenceError,
        OSError,
        Phase5CliError,
        Phase5PilotInputError,
        ValueError,
    ) as exc:
        payload = {
            "schema_version": "P5-OUTCOME-1",
            "status": Phase5Status.BLOCKED,
            "blockers": (type(exc).__name__.upper(),),
            "message": "Phase 5 request could not be represented safely",
        }
    print(
        json.dumps(
            public_data(payload),
            ensure_ascii=False,
            sort_keys=True,
            indent=2 if arguments.json_output else None,
        )
    )
    return (
        0
        if payload.get("status")
        in {
            Phase5Status.PASS,
            Phase5Status.PASS_WITH_LIMITATIONS,
        }
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
