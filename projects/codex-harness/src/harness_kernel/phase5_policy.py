"""Exact package eligibility and authorization for the Phase 5 pilot."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .phase3_models import CapabilityRecord
from .phase4_models import (
    CapabilityExecutionAuthorization,
    CapabilityInvocationRequest,
    ContextManifest,
    ExecutionMode,
    digest_payload,
    stable_digest_payload,
)
from .phase5_models import (
    FIXED_GRAPH,
    CapabilityFingerprint,
    EligibilityReport,
    Phase5Budget,
    Phase5Role,
    Phase5Status,
    Phase5Task,
)


class Phase5PolicyError(ValueError):
    """Raised when Phase 5 policy data cannot be represented safely."""


DEFAULT_BUILDER_TIMEOUT_SECONDS = 120
_BLOCKED_STATUSES = {"REJECTED", "INCOMPATIBLE", "STALE", "AMBIGUOUS"}
_BUILDER_POLICY_FIELDS = {
    "status",
    "execution_approved",
    "allowed_mode",
    "allow_tools",
    "allow_scripts",
    "allow_shell",
    "allow_network",
    "allow_mcp",
    "allow_providers",
    "allow_credentials",
    "scripts_metadata_only",
    "reason",
}


def _required_text(value: object, name: str, *, maximum: int = 4_096) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > maximum:
        raise Phase5PolicyError(f"{name} is invalid")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise Phase5PolicyError(f"{name} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or "\x00" in item:
            raise Phase5PolicyError(f"{name} contains an invalid string")
        if item not in result:
            result.append(item)
    return tuple(result)


def _bool(value: object, name: str, *, default: bool = False) -> bool:
    candidate = default if value is None else value
    if not isinstance(candidate, bool):
        raise Phase5PolicyError(f"{name} must be boolean")
    return candidate


def build_fingerprint(record: CapabilityRecord) -> CapabilityFingerprint:
    """Project Phase 3's immutable observation into the Phase 5 exact identity."""

    manifest_fingerprint = stable_digest_payload(record.manifest)
    return CapabilityFingerprint(
        capability_id=record.capability_id,
        version=record.version,
        scope=record.scope.value,
        canonical_path=record.path,
        package_fingerprint=record.content_hash,
        manifest_fingerprint=manifest_fingerprint,
        provenance=record.provenance.source_type,
        trust=record.trust.level.value,
        compatibility=record.compatibility.status.value,
        package_status=record.status.value,
        load_eligibility=record.load_eligibility,
        files=tuple(item.relative_path for item in record.files),
        scripts=record.scripts,
        dependencies=record.dependencies,
        # Phase 3 exposes script entries as metadata with execution disabled.
        scripts_metadata_only=True,
    )


@dataclass(frozen=True, slots=True)
class Phase5Allowlist:
    builder: CapabilityFingerprint
    builder_manifest_fingerprint: str
    approved_status: str
    secondary_status: str = "BLOCKED"
    secondary_blocker: str = "EXTERNAL_VERIFIER_NOT_ELIGIBLE"

    def __post_init__(self) -> None:
        if self.builder.capability_id != "design-director":
            raise Phase5PolicyError("the Phase 5 builder must be design-director")
        if self.builder.manifest_fingerprint != self.builder_manifest_fingerprint:
            raise Phase5PolicyError("builder manifest fingerprint is not bound")
        _required_text(self.approved_status, "approved_status", maximum=256)
        _required_text(self.secondary_status, "secondary_status", maximum=256)
        _required_text(self.secondary_blocker, "secondary_blocker", maximum=512)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> Phase5Allowlist:
        if payload.get("schema_version") != "P5-POLICY-1":
            raise Phase5PolicyError("unsupported Phase 5 policy schema")
        allowed = {
            "schema_version",
            "policy_id",
            "builder",
            "secondary",
            "graph",
            "budgets",
            "builder_manifest_fingerprint",
            "approved_status",
            "secondary_status",
            "secondary_blocker",
        }
        if set(payload).difference(allowed):
            raise Phase5PolicyError("policy contains unsupported fields")
        if "graph" not in payload or "budgets" not in payload:
            raise Phase5PolicyError("policy must declare the fixed graph and budgets")
        raw_graph = payload.get("graph")
        if not isinstance(raw_graph, (list, tuple)) or tuple(raw_graph) != FIXED_GRAPH:
            raise Phase5PolicyError("policy graph does not match the fixed Phase 5 graph")
        expected_budget = Phase5Budget()
        budget_fields = {
            field: getattr(expected_budget, field)
            for field in (
                "max_builder_invocations",
                "max_structural_verifications",
                "max_visual_critiques",
                "max_repairs",
                "max_render_versions",
                "max_artifact_bytes",
                "max_context_bytes",
                "max_evidence_records",
            )
        }
        raw_budgets = payload.get("budgets")
        if not isinstance(raw_budgets, Mapping) or set(raw_budgets) != set(budget_fields):
            raise Phase5PolicyError("policy budgets are incomplete or unsupported")
        if any(raw_budgets.get(field) != value for field, value in budget_fields.items()):
            raise Phase5PolicyError("policy budgets do not match the fixed Phase 5 budgets")
        raw_builder = payload.get("builder")
        if isinstance(raw_builder, CapabilityFingerprint):
            builder = raw_builder
        elif isinstance(raw_builder, Mapping):
            builder = _fingerprint_from_mapping(raw_builder)
        else:
            raise Phase5PolicyError("builder fingerprint is required")
        secondary = payload.get("secondary")
        if not isinstance(secondary, Mapping):
            secondary = {}
        if isinstance(raw_builder, Mapping):
            _validate_builder_action_policy(raw_builder)
        secondary_status = payload.get("secondary_status", secondary.get("status", "BLOCKED"))
        secondary_blocker = payload.get(
            "secondary_blocker",
            secondary.get("blocker", "EXTERNAL_VERIFIER_NOT_ELIGIBLE"),
        )
        manifest = payload.get("builder_manifest_fingerprint", builder.manifest_fingerprint)
        if not isinstance(manifest, str):
            raise Phase5PolicyError("builder manifest fingerprint is required")
        return cls(
            builder=builder,
            builder_manifest_fingerprint=manifest,
            approved_status=_required_text(
                payload.get("approved_status", "APPROVED_RESPONSE_ONLY"), "approved_status"
            ),
            secondary_status=_required_text(secondary_status, "secondary_status"),
            secondary_blocker=_required_text(secondary_blocker, "secondary_blocker"),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> Phase5Allowlist:
        candidate = Path(path)
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise Phase5PolicyError("Phase 5 policy cannot be read safely") from exc
        if not isinstance(payload, Mapping):
            raise Phase5PolicyError("Phase 5 policy must contain an object")
        return cls.from_mapping(payload)


def _fingerprint_from_mapping(payload: Mapping[str, object]) -> CapabilityFingerprint:
    fields = {
        "capability_id",
        "version",
        "scope",
        "canonical_path",
        "package_fingerprint",
        "manifest_fingerprint",
        "provenance",
        "trust",
        "compatibility",
        "package_status",
        "load_eligibility",
        "files",
        "scripts",
        "dependencies",
        "scripts_metadata_only",
    } | _BUILDER_POLICY_FIELDS
    if set(payload).difference(fields):
        raise Phase5PolicyError("builder fingerprint contains unsupported fields")
    return CapabilityFingerprint(
        capability_id=_required_text(payload.get("capability_id"), "capability_id"),
        version=_required_text(payload.get("version"), "version"),
        scope=_required_text(payload.get("scope"), "scope"),
        canonical_path=_required_text(payload.get("canonical_path"), "canonical_path"),
        package_fingerprint=_required_text(
            payload.get("package_fingerprint"), "package_fingerprint"
        ),
        manifest_fingerprint=(
            _required_text(payload.get("manifest_fingerprint"), "manifest_fingerprint")
            if payload.get("manifest_fingerprint") is not None
            else None
        ),
        provenance=_required_text(payload.get("provenance", "LOCAL"), "provenance"),
        trust=_required_text(payload.get("trust", "PROJECT_TRUSTED"), "trust"),
        compatibility=_required_text(payload.get("compatibility", "COMPATIBLE"), "compatibility"),
        package_status=_required_text(payload.get("package_status", "INSPECTED"), "package_status"),
        load_eligibility=_required_text(
            payload.get("load_eligibility", "ELIGIBLE_DECLARATIVE_METADATA_ONLY"),
            "load_eligibility",
        ),
        files=_strings(payload.get("files"), "files"),
        scripts=_strings(payload.get("scripts"), "scripts"),
        dependencies=_strings(payload.get("dependencies"), "dependencies"),
        scripts_metadata_only=_bool(payload.get("scripts_metadata_only"), "scripts_metadata_only"),
    )


def _validate_builder_action_policy(payload: Mapping[str, object]) -> None:
    status = payload.get("status", "APPROVED_RESPONSE_ONLY")
    if status != "APPROVED_RESPONSE_ONLY":
        raise Phase5PolicyError("builder action policy is not approved")
    execution_approved = payload.get("execution_approved", True)
    if not isinstance(execution_approved, bool) or not execution_approved:
        raise Phase5PolicyError("builder execution approval is required")
    mode = payload.get("allowed_mode", "RESPONSE_ONLY_BUILDER")
    if mode != "RESPONSE_ONLY_BUILDER":
        raise Phase5PolicyError("builder mode is not response-only")
    for name in (
        "allow_tools",
        "allow_scripts",
        "allow_shell",
        "allow_network",
        "allow_mcp",
        "allow_providers",
        "allow_credentials",
    ):
        value = payload.get(name, False)
        if not isinstance(value, bool) or value:
            raise Phase5PolicyError(f"builder policy must deny {name.removeprefix('allow_')}")
    scripts_metadata_only = payload.get("scripts_metadata_only", True)
    if not isinstance(scripts_metadata_only, bool) or not scripts_metadata_only:
        raise Phase5PolicyError("builder scripts must remain metadata-only")
    reason = payload.get("reason", "")
    if not isinstance(reason, str) or not reason or "\x00" in reason:
        raise Phase5PolicyError("builder policy reason is invalid")


def evaluate_eligibility(
    fingerprint: CapabilityFingerprint,
    allowlist: Phase5Allowlist,
    role: Phase5Role,
    *,
    now: int | None = None,
) -> EligibilityReport:
    """Evaluate an exact, narrow role permission; routability is not permission."""

    evaluated_at = int(time.time()) if now is None else now
    reasons: list[str] = []
    blockers: list[str] = []
    if role is not Phase5Role.DESIGN_BUILDER:
        blockers.append("SECONDARY_CAPABILITY_NOT_ELIGIBLE")
        route = "NATIVE_HARNESS_FALLBACK"
    else:
        route = "RESPONSE_ONLY_BUILDER"
        expected = allowlist.builder
        comparisons = (
            ("CAPABILITY_ID_MISMATCH", fingerprint.capability_id, expected.capability_id),
            ("VERSION_MISMATCH", fingerprint.version, expected.version),
            ("SCOPE_MISMATCH", fingerprint.scope, expected.scope),
            ("CANONICAL_PATH_MISMATCH", fingerprint.canonical_path, expected.canonical_path),
            (
                "PACKAGE_FINGERPRINT_MISMATCH",
                fingerprint.package_fingerprint,
                expected.package_fingerprint,
            ),
            (
                "MANIFEST_FINGERPRINT_MISMATCH",
                fingerprint.manifest_fingerprint,
                expected.manifest_fingerprint,
            ),
        )
        for blocker, observed, approved in comparisons:
            if observed != approved:
                blockers.append(blocker)
        if fingerprint.package_status in _BLOCKED_STATUSES:
            blockers.append("PACKAGE_STATUS_BLOCKED")
        if fingerprint.trust == "REJECTED":
            blockers.append("TRUST_REJECTED")
        if fingerprint.compatibility == "INCOMPATIBLE":
            blockers.append("COMPATIBILITY_INCOMPATIBLE")
        if fingerprint.load_eligibility.startswith("BLOCKED"):
            blockers.append("LOAD_ELIGIBILITY_BLOCKED")
        if fingerprint.dependencies:
            blockers.append("DEPENDENCY_NOT_APPROVED")
        if fingerprint.scripts and not fingerprint.scripts_metadata_only:
            blockers.append("PACKAGE_SCRIPTS_PRESENT")
        elif fingerprint.scripts:
            reasons.append("PACKAGE_SCRIPTS_METADATA_ONLY_AND_DISABLED")
        if allowlist.approved_status != "APPROVED_RESPONSE_ONLY":
            blockers.append("BUILDER_POLICY_NOT_APPROVED")
        if not blockers:
            reasons.extend(
                (
                    "EXACT_PACKAGE_IDENTITY_MATCH",
                    "RESPONSE_ONLY_ARTIFACT_MATERIALIZATION",
                    "HOST_ACTIONS_DENIED",
                )
            )
    status = Phase5Status.PASS if not blockers else Phase5Status.BLOCKED
    return EligibilityReport(
        capability_id=fingerprint.capability_id,
        role=role,
        status=status,
        route=route,
        fingerprint=fingerprint,
        reasons=tuple(reasons),
        blockers=tuple(dict.fromkeys(blockers)),
        inspected_files=fingerprint.files,
        evaluated_at=evaluated_at,
    )


def validate_fixed_graph(graph: tuple[str, ...]) -> None:
    if tuple(graph) != FIXED_GRAPH:
        raise ValueError("Phase 5 graph must match the fixed bounded graph")


def _builder_prompt(task: Phase5Task, repair_instruction: str | None = None) -> str:
    exact_copy = json.dumps(dict(task.brief.exact_copy), ensure_ascii=False, sort_keys=True)
    criteria = "\n".join(f"- {item}" for item in task.criteria.serialized)
    include = ", ".join(task.brief.must_include)
    avoid = ", ".join(task.brief.must_avoid)
    prompt = (
        f"{task.request}\n\n"
        f"Audience: {task.brief.audience}\nJob: {task.brief.job}\n"
        f"Design thesis: {task.brief.thesis}\nMedium: {task.brief.medium}\n"
        f"Primary action: {task.brief.primary_action}\n"
        f"Exact copy JSON (preserve verbatim): {exact_copy}\n"
        f"Must include: {include}\nMust avoid: {avoid}\n"
        f"Responsive intent: {task.brief.responsive_intent}\n"
        f"Accessibility intent: {task.brief.accessibility_intent}\n"
        f"Asset role: {task.brief.asset_role}\n"
        f"Acceptance criteria:\n{criteria}\n\n"
        "Return exactly one JSON object with no Markdown fences and these keys: "
        "artifact_filename (exactly index.html) and "
        "artifact_html (the complete standalone HTML document). "
        "Use only inline CSS/SVG, no script tags, no event handlers, "
        "no remote URLs and no external assets."
    )
    if repair_instruction is not None:
        if (
            not isinstance(repair_instruction, str)
            or not repair_instruction
            or "\x00" in repair_instruction
        ):
            raise Phase5PolicyError("repair instruction is invalid")
        if len(repair_instruction) > 4_096:
            raise Phase5PolicyError("repair instruction exceeds its bound")
        prompt += (
            "\n\nBounded repair instruction from the blind critic (apply only this correction; "
            "preserve the task brief and exact copy):\n" + repair_instruction
        )
    return prompt


def build_builder_request(
    task: Phase5Task,
    fingerprint: CapabilityFingerprint,
    *,
    host_executable_digest: str,
    host_interpreter_digest: str,
    attempt: int,
    now: int | None = None,
    budget: Phase5Budget | None = None,
    repair_instruction: str | None = None,
) -> CapabilityInvocationRequest:
    if attempt < 1:
        raise Phase5PolicyError("builder attempt must be positive")
    selected_budget = budget or Phase5Budget()
    prompt = _builder_prompt(task, repair_instruction)
    issued_at = int(time.time()) if now is None else now
    skill_path = str(Path(fingerprint.canonical_path) / "SKILL.md")
    context_payload = {
        "task_id": task.task_id,
        "task_digest": digest_payload(prompt),
        "capability_id": fingerprint.capability_id,
        "package_fingerprint": fingerprint.package_fingerprint,
        "skill_path": skill_path,
        "sources": ("HOST_MANAGED_SKILL",),
        "selected_references": fingerprint.files,
        "omitted_references": (),
        "estimated_bytes": selected_budget.max_context_bytes // 2,
        "acceptance_criteria": task.criteria.serialized,
    }
    context = ContextManifest(
        task_id=task.task_id,
        task_digest=digest_payload(prompt),
        capability_id=fingerprint.capability_id,
        package_fingerprint=fingerprint.package_fingerprint,
        skill_path=skill_path,
        sources=("HOST_MANAGED_SKILL",),
        selected_references=fingerprint.files,
        omitted_references=(),
        estimated_bytes=selected_budget.max_context_bytes // 2,
        digest=stable_digest_payload(context_payload, workspace=task.workspace),
        acceptance_criteria=task.criteria.serialized,
    )
    authorization_payload = {
        "task_id": task.task_id,
        "run_id": task.run_id,
        "capability_id": fingerprint.capability_id,
        "version": fingerprint.version,
        "package_fingerprint": fingerprint.package_fingerprint,
        "context_digest": context.digest,
        "attempt": attempt,
        "issued_at": issued_at,
    }
    authorization_id = (
        "AUTH-P5-" + uuid.uuid5(uuid.NAMESPACE_URL, digest_payload(authorization_payload)).hex[:24]
    )
    authorization = CapabilityExecutionAuthorization(
        authorization_id=authorization_id,
        task_id=task.task_id,
        run_id=task.run_id,
        capability_id=fingerprint.capability_id,
        capability_version=fingerprint.version,
        package_fingerprint=fingerprint.package_fingerprint,
        scope=fingerprint.scope,
        requested_loading_level="L2_INSTRUCTION_KERNEL",
        requested_execution_mode=ExecutionMode.CONTROLLED_REAL,
        allowed_tools=(),
        allowed_side_effects=(),
        filesystem_policy={
            "workspace": task.workspace,
            "mode": "READ_ONLY",
            "artifact_root": task.artifact_root,
            "host_executable_digest": host_executable_digest,
            "host_interpreter_digest": host_interpreter_digest,
        },
        network_policy="DENY",
        shell_policy="DENY",
        provider_policy="DENY",
        mcp_policy="DENY",
        credential_policy="DENY",
        timeout_seconds=DEFAULT_BUILDER_TIMEOUT_SECONDS,
        iteration_budget={"host_calls": 1, "tool_calls": 0, "repair_iterations": 0},
        context_budget={"max_bytes": selected_budget.max_context_bytes},
        artifact_policy={
            "types": ("HOST_RESPONSE",),
            "max_count": 1,
            "max_bytes": selected_budget.max_artifact_bytes,
        },
        evidence_policy={"max_events": 256, "max_count": selected_budget.max_evidence_records},
        issued_by="phase5-preflight",
        issued_at=issued_at,
        expires_at=issued_at + DEFAULT_BUILDER_TIMEOUT_SECONDS,
        reason="Exact design-director response-only builder pilot",
        constraints=(
            "no scripts",
            "no tools",
            "no shell",
            "no network",
            "no MCP",
            "no providers",
            "no credentials",
            "no subagents",
            "no host file changes",
        ),
        host_executable_digest=host_executable_digest,
        host_interpreter_digest=host_interpreter_digest,
    )
    invocation_id = (
        "INV-P5-"
        + uuid.uuid5(
            uuid.NAMESPACE_URL,
            digest_payload(
                {
                    "task": task.task_id,
                    "run": task.run_id,
                    "context": context.digest,
                    "attempt": attempt,
                }
            ),
        ).hex[:24]
    )
    return CapabilityInvocationRequest(
        invocation_id=invocation_id,
        authorization=authorization,
        context=context,
        skill_name=fingerprint.capability_id,
        skill_path=skill_path,
        task=prompt,
        acceptance_criteria=task.criteria.serialized,
        workspace=task.workspace,
        expected_artifacts=("HOST_RESPONSE",),
        idempotency_key="IDEM-" + invocation_id.removeprefix("INV-"),
    )
