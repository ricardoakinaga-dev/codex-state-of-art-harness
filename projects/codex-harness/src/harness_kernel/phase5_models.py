"""Immutable contracts for the bounded Phase 5 visual composition pilot."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .phase4_models import digest_payload


class Phase5Enum(StrEnum):
    def __str__(self) -> str:
        return self.value


class Phase5Status(Phase5Enum):
    PASS = "PASS"
    PASS_WITH_LIMITATIONS = "PASS_WITH_LIMITATIONS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    STALE = "STALE"
    NOT_RUN = "NOT_RUN"


class FindingSeverity(Phase5Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    POLISH = "POLISH"


class Phase5Role(Phase5Enum):
    ROUTER = "ROUTER"
    DESIGN_BUILDER = "DESIGN_BUILDER"
    STRUCTURAL_VERIFIER = "STRUCTURAL_VERIFICATION"
    VISUAL_CRITIC = "VISUAL_CRITIQUE"
    REPAIRER = "OPTIONAL_REPAIR"
    FINAL_VERIFIER = "FINAL_VERIFICATION"
    ASSURANCE = "ASSURANCE"


FIXED_GRAPH = (
    Phase5Role.DESIGN_BUILDER.value,
    Phase5Role.STRUCTURAL_VERIFIER.value,
    Phase5Role.VISUAL_CRITIC.value,
    Phase5Role.REPAIRER.value,
    Phase5Role.FINAL_VERIFIER.value,
    Phase5Role.ASSURANCE.value,
)
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_TEXT = 32_768


def _text(value: object, name: str, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > maximum:
        raise ValueError(f"{name} is invalid")
    return value


def _digest(value: str, name: str) -> None:
    if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a sha256 digest")


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _strings(values: object, name: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or (not value and not allow_empty) or "\x00" in value:
            raise ValueError(f"{name} contains an invalid string")
        if value not in result:
            result.append(value)
    return tuple(result)


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


def _mapping(value: Mapping[str, object], name: str) -> Mapping[str, object]:
    frozen = _freeze(value)
    if not isinstance(frozen, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return frozen


def _safe_absolute(path_value: str, name: str) -> Path:
    path = Path(_text(path_value, name, maximum=4_096))
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError(f"{name} must be an absolute non-traversing path")
    return path


def _under(path: Path, root: Path, name: str) -> None:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ValueError(f"{name} must remain inside the workspace") from exc


@dataclass(frozen=True, slots=True)
class Phase5Budget:
    max_builder_invocations: int = 2
    max_structural_verifications: int = 2
    max_visual_critiques: int = 2
    max_repairs: int = 1
    max_render_versions: int = 2
    max_artifact_bytes: int = 131_072
    max_context_bytes: int = 32_768
    max_evidence_records: int = 64

    def __post_init__(self) -> None:
        expected = {
            "max_builder_invocations": 2,
            "max_structural_verifications": 2,
            "max_visual_critiques": 2,
            "max_repairs": 1,
            "max_render_versions": 2,
            "max_artifact_bytes": 131_072,
            "max_context_bytes": 32_768,
            "max_evidence_records": 64,
        }
        for name in (
            "max_builder_invocations",
            "max_structural_verifications",
            "max_visual_critiques",
            "max_repairs",
            "max_render_versions",
            "max_artifact_bytes",
            "max_context_bytes",
            "max_evidence_records",
        ):
            _integer(getattr(self, name), name, minimum=1)
        for name, value in expected.items():
            if getattr(self, name) != value:
                raise ValueError(f"{name} does not match the fixed Phase 5 budget")


@dataclass(frozen=True, slots=True)
class CapabilityFingerprint:
    capability_id: str
    version: str
    scope: str
    canonical_path: str
    package_fingerprint: str
    manifest_fingerprint: str | None
    provenance: str
    trust: str
    compatibility: str
    package_status: str
    load_eligibility: str
    files: tuple[str, ...]
    scripts: tuple[str, ...]
    dependencies: tuple[str, ...]
    scripts_metadata_only: bool = False

    def __post_init__(self) -> None:
        for name in (
            "capability_id",
            "version",
            "scope",
            "provenance",
            "trust",
            "compatibility",
            "package_status",
            "load_eligibility",
        ):
            _text(getattr(self, name), name, maximum=512)
        _safe_absolute(self.canonical_path, "canonical_path")
        _digest(self.package_fingerprint, "package_fingerprint")
        if self.manifest_fingerprint is not None:
            _digest(self.manifest_fingerprint, "manifest_fingerprint")
        for name in ("files", "scripts", "dependencies"):
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        if not isinstance(self.scripts_metadata_only, bool):
            raise ValueError("scripts_metadata_only must be boolean")


@dataclass(frozen=True, slots=True)
class VisualBrief:
    outcome: str
    audience: str
    job: str
    thesis: str
    medium: str
    primary_action: str
    exact_copy: Mapping[str, str]
    must_include: tuple[str, ...]
    must_avoid: tuple[str, ...]
    responsive_intent: str
    accessibility_intent: str
    asset_role: str

    def __post_init__(self) -> None:
        for name in (
            "outcome",
            "audience",
            "job",
            "thesis",
            "medium",
            "primary_action",
            "responsive_intent",
            "accessibility_intent",
            "asset_role",
        ):
            _text(getattr(self, name), name)
        copy = _mapping(self.exact_copy, "exact_copy")
        if any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in copy.items()
        ):
            raise ValueError("exact_copy must map strings to strings")
        object.__setattr__(self, "exact_copy", copy)
        object.__setattr__(self, "must_include", _strings(self.must_include, "must_include"))
        object.__setattr__(self, "must_avoid", _strings(self.must_avoid, "must_avoid"))


@dataclass(frozen=True, slots=True)
class AcceptanceCriteria:
    required_sections: tuple[str, ...] = ("header", "main", "footer")
    required_copy: tuple[str, ...] = ()
    render_viewports: tuple[tuple[int, int], ...] = ((1440, 900), (390, 844))
    dimensions: tuple[str, ...] = ("ART_DIRECTION",)
    forbidden_signals: tuple[str, ...] = ()
    max_artifact_bytes: int = 131_072

    def __post_init__(self) -> None:
        for name in ("required_sections", "required_copy", "dimensions", "forbidden_signals"):
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        if not self.required_sections:
            raise ValueError("required_sections cannot be empty")
        if not self.dimensions:
            raise ValueError("dimensions cannot be empty")
        viewports: list[tuple[int, int]] = []
        if not isinstance(self.render_viewports, (list, tuple)) or not self.render_viewports:
            raise ValueError("render_viewports cannot be empty")
        for value in self.render_viewports:
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError("viewport must contain width and height")
            width = _integer(value[0], "viewport width", minimum=1)
            height = _integer(value[1], "viewport height", minimum=1)
            if width > 10_000 or height > 10_000:
                raise ValueError("viewport is too large")
            item = (width, height)
            if item not in viewports:
                viewports.append(item)
        object.__setattr__(self, "render_viewports", tuple(viewports))
        _integer(self.max_artifact_bytes, "max_artifact_bytes", minimum=1)

    @property
    def serialized(self) -> tuple[str, ...]:
        return (
            *(f"section:{item}" for item in self.required_sections),
            *(f"copy:{item}" for item in self.required_copy),
            *(f"viewport:{width}x{height}" for width, height in self.render_viewports),
            *(f"dimension:{item}" for item in self.dimensions),
            *(f"forbidden:{item}" for item in self.forbidden_signals),
        )

    @property
    def digest(self) -> str:
        return digest_payload(
            {
                "required_sections": self.required_sections,
                "required_copy": self.required_copy,
                "render_viewports": self.render_viewports,
                "dimensions": self.dimensions,
                "forbidden_signals": self.forbidden_signals,
                "max_artifact_bytes": self.max_artifact_bytes,
            }
        )


@dataclass(frozen=True, slots=True)
class Phase5Task:
    task_id: str
    run_id: str
    title: str
    request: str
    workspace: str
    artifact_root: str
    brief: VisualBrief
    criteria: AcceptanceCriteria
    created_at: int

    def __post_init__(self) -> None:
        for name in ("task_id", "run_id", "title", "request"):
            _text(getattr(self, name), name, maximum=16_384 if name == "request" else 2_048)
        workspace = _safe_absolute(self.workspace, "workspace")
        artifact_root = _safe_absolute(self.artifact_root, "artifact_root")
        _under(artifact_root, workspace, "artifact_root")
        object.__setattr__(self, "workspace", str(workspace))
        object.__setattr__(self, "artifact_root", str(artifact_root))
        _integer(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class EligibilityReport:
    capability_id: str
    role: Phase5Role
    status: Phase5Status
    route: str
    fingerprint: CapabilityFingerprint
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    inspected_files: tuple[str, ...]
    evaluated_at: int
    digest: str = ""

    def __post_init__(self) -> None:
        _text(self.capability_id, "capability_id")
        if not isinstance(self.role, Phase5Role) or not isinstance(self.status, Phase5Status):
            raise ValueError("eligibility role/status is invalid")
        _text(self.route, "route", maximum=256)
        object.__setattr__(self, "reasons", _strings(self.reasons, "reasons"))
        object.__setattr__(self, "blockers", _strings(self.blockers, "blockers"))
        object.__setattr__(
            self, "inspected_files", _strings(self.inspected_files, "inspected_files")
        )
        _integer(self.evaluated_at, "evaluated_at")
        digest = self.digest or digest_payload(
            {
                "capability_id": self.capability_id,
                "role": self.role,
                "status": self.status,
                "route": self.route,
                "fingerprint": self.fingerprint,
                "reasons": self.reasons,
                "blockers": self.blockers,
                "inspected_files": self.inspected_files,
                "evaluated_at": self.evaluated_at,
            }
        )
        _digest(digest, "digest")
        object.__setattr__(self, "digest", digest)
        if self.status is Phase5Status.PASS and self.blockers:
            raise ValueError("an eligible report cannot contain blockers")


@dataclass(frozen=True, slots=True)
class ArtifactPacket:
    artifact_id: str
    version: str
    path: str
    digest: str
    size_bytes: int
    producer_capability: str
    invocation_id: str
    task_id: str
    acceptance_digest: str
    source_kind: str
    parent_artifact_digest: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "artifact_id",
            "version",
            "path",
            "producer_capability",
            "invocation_id",
            "task_id",
            "source_kind",
        ):
            _text(getattr(self, name), name, maximum=4_096)
        _safe_absolute(self.path, "path")
        _digest(self.digest, "digest")
        _digest(self.acceptance_digest, "acceptance_digest")
        if self.parent_artifact_digest is not None:
            _digest(self.parent_artifact_digest, "parent_artifact_digest")
        _integer(self.size_bytes, "size_bytes", minimum=1)
        if self.version not in {"artifact_v1", "artifact_v2"}:
            raise ValueError("artifact version is invalid")

    @classmethod
    def from_content(
        cls,
        *,
        artifact_id: str,
        version: str,
        path: str,
        content: str,
        producer_capability: str,
        invocation_id: str,
        task: Phase5Task,
        parent_artifact_digest: str | None = None,
    ) -> ArtifactPacket:
        _text(content, "content", maximum=task.criteria.max_artifact_bytes)
        if not content.strip().lower().startswith(("<!doctype html", "<html")):
            raise ValueError("response artifact must be an HTML document")
        candidate = _safe_absolute(path, "path")
        _under(candidate, Path(task.artifact_root), "artifact path")
        raw = content.encode("utf-8")
        return cls(
            artifact_id=artifact_id,
            version=version,
            path=str(candidate),
            digest="sha256:" + hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
            producer_capability=producer_capability,
            invocation_id=invocation_id,
            task_id=task.task_id,
            acceptance_digest=task.criteria.digest,
            source_kind="HOST_RESPONSE_DERIVED",
            parent_artifact_digest=parent_artifact_digest,
        )


@dataclass(frozen=True, slots=True)
class RenderRecord:
    render_id: str
    artifact_version: str
    path: str
    viewport: tuple[int, int]
    digest: str
    size_bytes: int
    captured_by: str = "playwright"
    captured_at: int = 0

    def __post_init__(self) -> None:
        for name in ("render_id", "artifact_version", "path", "captured_by"):
            _text(getattr(self, name), name, maximum=4_096)
        _safe_absolute(self.path, "path")
        if self.artifact_version not in {"artifact_v1", "artifact_v2"}:
            raise ValueError("render artifact version is invalid")
        if not isinstance(self.viewport, (list, tuple)) or len(self.viewport) != 2:
            raise ValueError("viewport is invalid")
        _integer(self.viewport[0], "viewport width", minimum=1)
        _integer(self.viewport[1], "viewport height", minimum=1)
        object.__setattr__(self, "viewport", (self.viewport[0], self.viewport[1]))
        _digest(self.digest, "digest")
        _integer(self.size_bytes, "size_bytes", minimum=1)
        _integer(self.captured_at, "captured_at")

    @classmethod
    def from_file(
        cls,
        render_id: str,
        artifact_version: str,
        path: str | Path,
        viewport: tuple[int, int],
        *,
        root: str | Path,
        captured_by: str = "playwright",
        captured_at: int = 0,
    ) -> RenderRecord:
        candidate = Path(path)
        root_path = Path(root)
        if not candidate.is_absolute() or not root_path.is_absolute():
            raise ValueError("render and root paths must be absolute")
        if any(part in {"", ".", ".."} for part in candidate.parts):
            raise ValueError("render path contains an unsafe component")
        try:
            metadata = candidate.lstat()
            resolved_root = root_path.resolve(strict=True)
            resolved_candidate = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError("render file cannot be read") from exc
        current = Path(candidate.anchor)
        for part in candidate.parts[1:]:
            current /= part
            try:
                component = current.lstat()
            except OSError as exc:
                raise ValueError("render path cannot be inspected") from exc
            if stat.S_ISLNK(component.st_mode):
                raise ValueError("render path cannot contain symlinks")
        if not resolved_candidate.is_relative_to(resolved_root):
            raise ValueError("render path must remain inside its root")
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("render file must be a regular file")
        try:
            raw = candidate.read_bytes()
        except OSError as exc:
            raise ValueError("render file cannot be read") from exc
        return cls(
            render_id=render_id,
            artifact_version=artifact_version,
            path=str(candidate),
            viewport=viewport,
            digest="sha256:" + hashlib.sha256(raw).hexdigest(),
            size_bytes=metadata.st_size,
            captured_by=captured_by,
            captured_at=captured_at,
        )


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    location: str
    expected: str
    observed: str
    severity: FindingSeverity
    evidence: str
    status: str = "OPEN"

    def __post_init__(self) -> None:
        for name in ("finding_id", "location", "expected", "observed", "evidence", "status"):
            _text(getattr(self, name), name, maximum=8_192)
        if not isinstance(self.severity, FindingSeverity):
            raise ValueError("finding severity is invalid")


@dataclass(frozen=True, slots=True)
class StructuralVerification:
    verification_id: str
    artifact_version: str
    artifact_digest: str
    status: Phase5Status
    checks: tuple[str, ...]
    findings: tuple[Finding, ...]
    render_refs: tuple[str, ...]
    console_errors: tuple[str, ...] = ()
    network_failures: tuple[str, ...] = ()
    created_at: int = 0
    digest: str = ""

    def __post_init__(self) -> None:
        _text(self.verification_id, "verification_id")
        _digest(self.artifact_digest, "artifact_digest")
        if not isinstance(self.status, Phase5Status):
            raise ValueError("verification status is invalid")
        for name in ("checks", "render_refs", "console_errors", "network_failures"):
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        object.__setattr__(self, "findings", tuple(self.findings))
        if any(not isinstance(item, Finding) for item in self.findings):
            raise ValueError("findings contain an invalid record")
        _integer(self.created_at, "created_at")
        digest = self.digest or digest_payload(
            {
                "verification_id": self.verification_id,
                "artifact_version": self.artifact_version,
                "artifact_digest": self.artifact_digest,
                "status": self.status,
                "checks": self.checks,
                "findings": self.findings,
                "render_refs": self.render_refs,
                "console_errors": self.console_errors,
                "network_failures": self.network_failures,
                "created_at": self.created_at,
            }
        )
        _digest(digest, "digest")
        object.__setattr__(self, "digest", digest)


@dataclass(frozen=True, slots=True)
class BlindPacket:
    benchmark_id: str
    run_id: str
    artifact: ArtifactPacket
    renders: tuple[RenderRecord, ...]
    acceptance_criteria: tuple[str, ...]
    packet_digest: str
    builder_rationale_withheld: bool = True
    self_score_withheld: bool = True

    def __post_init__(self) -> None:
        _text(self.benchmark_id, "benchmark_id")
        _text(self.run_id, "run_id")
        object.__setattr__(self, "renders", tuple(self.renders))
        if any(not isinstance(item, RenderRecord) for item in self.renders):
            raise ValueError("renders contain an invalid record")
        object.__setattr__(
            self, "acceptance_criteria", _strings(self.acceptance_criteria, "acceptance_criteria")
        )
        _digest(self.packet_digest, "packet_digest")
        if not isinstance(self.builder_rationale_withheld, bool) or not isinstance(
            self.self_score_withheld, bool
        ):
            raise ValueError("blind packet flags are invalid")
        if not self.builder_rationale_withheld or not self.self_score_withheld:
            raise ValueError("blind packet cannot contain builder rationale or self-score")


@dataclass(frozen=True, slots=True)
class VisualCritique:
    benchmark_id: str
    run_id: str
    inspection_id: str
    artifact_digest: str
    independence: str
    blinded: bool
    builder_rationale_withheld: bool
    self_score_withheld: bool
    packet_digest: str
    verdict: Phase5Status
    overall_score: float | None
    evidence_confidence: str
    dimension_scores: Mapping[str, float]
    findings: tuple[Finding, ...]
    top_corrections: tuple[str, ...]
    evidence_missing: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "benchmark_id",
            "run_id",
            "inspection_id",
            "independence",
            "evidence_confidence",
        ):
            _text(getattr(self, name), name, maximum=512)
        _digest(self.artifact_digest, "artifact_digest")
        _digest(self.packet_digest, "packet_digest")
        if not isinstance(self.verdict, Phase5Status):
            raise ValueError("critique verdict is invalid")
        if not isinstance(self.blinded, bool) or not isinstance(
            self.builder_rationale_withheld, bool
        ):
            raise ValueError("critique blind flags are invalid")
        if not isinstance(self.self_score_withheld, bool):
            raise ValueError("critique self-score flag is invalid")
        if self.independence not in {"INDEPENDENT", "BLOCKED"}:
            raise ValueError("critic independence is invalid")
        if self.independence == "INDEPENDENT" and (
            not self.blinded or not self.builder_rationale_withheld or not self.self_score_withheld
        ):
            raise ValueError("a visual critique cannot approve from the builder context")
        if self.independence == "BLOCKED" and self.verdict is not Phase5Status.BLOCKED:
            raise ValueError("blocked critic records must be blocked")
        if self.overall_score is not None and not 0 <= self.overall_score <= 100:
            raise ValueError("overall_score is outside 0..100")
        normalized: dict[str, float] = {}
        for key, value in self.dimension_scores.items():
            if (
                not isinstance(key, str)
                or not isinstance(value, (float, int))
                or not 0 <= value <= 10
            ):
                raise ValueError("dimension score is invalid")
            normalized[key] = float(value)
        object.__setattr__(self, "dimension_scores", MappingProxyType(normalized))
        object.__setattr__(self, "findings", tuple(self.findings))
        if any(not isinstance(item, Finding) for item in self.findings):
            raise ValueError("critique findings contain an invalid record")
        object.__setattr__(
            self, "top_corrections", _strings(self.top_corrections, "top_corrections")
        )
        object.__setattr__(
            self, "evidence_missing", _strings(self.evidence_missing, "evidence_missing")
        )

    @property
    def is_independent(self) -> bool:
        return self.independence == "INDEPENDENT"


@dataclass(frozen=True, slots=True)
class RepairPlan:
    source_artifact_version: str
    target_artifact_version: str
    owner: Phase5Role
    correction: str
    reason: str
    budget_remaining: int
    status: Phase5Status

    def __post_init__(self) -> None:
        if (
            self.source_artifact_version != "artifact_v1"
            or self.target_artifact_version != "artifact_v2"
        ):
            raise ValueError("repair must advance artifact_v1 to artifact_v2")
        if self.owner is not Phase5Role.REPAIRER:
            raise ValueError("repair owner is invalid")
        _text(self.correction, "correction")
        _text(self.reason, "reason")
        _integer(self.budget_remaining, "budget_remaining")
        if not isinstance(self.status, Phase5Status):
            raise ValueError("repair status is invalid")


@dataclass(frozen=True, slots=True)
class AssuranceReport:
    run_id: str
    status: Phase5Status
    support_level: str
    reason: str
    limitations: tuple[str, ...]
    blockers: tuple[str, ...]
    artifact_digest: str | None
    verification_digest: str | None
    critique_digest: str | None
    created_at: int = 0
    digest: str = ""

    def __post_init__(self) -> None:
        _text(self.run_id, "run_id")
        if not isinstance(self.status, Phase5Status):
            raise ValueError("assurance status is invalid")
        if self.support_level not in {"A", "B", "C", "NONE"}:
            raise ValueError("support level is invalid")
        _text(self.reason, "reason", maximum=8_192)
        object.__setattr__(self, "limitations", _strings(self.limitations, "limitations"))
        object.__setattr__(self, "blockers", _strings(self.blockers, "blockers"))
        for name in ("artifact_digest", "verification_digest", "critique_digest"):
            value = getattr(self, name)
            if value is not None:
                _digest(value, name)
        _integer(self.created_at, "created_at")
        digest = self.digest or digest_payload(
            {
                "run_id": self.run_id,
                "status": self.status,
                "support_level": self.support_level,
                "reason": self.reason,
                "limitations": self.limitations,
                "blockers": self.blockers,
                "artifact_digest": self.artifact_digest,
                "verification_digest": self.verification_digest,
                "critique_digest": self.critique_digest,
                "created_at": self.created_at,
            }
        )
        _digest(digest, "digest")
        object.__setattr__(self, "digest", digest)


@dataclass(frozen=True, slots=True)
class CompositionReceipt:
    task_id: str
    run_id: str
    status: Phase5Status
    graph: tuple[str, ...]
    events: tuple[str, ...]
    builder_invocations: int
    verifier_invocations: int
    critic_invocations: int
    repair_invocations: int
    artifact_versions: tuple[str, ...]
    stale_evidence: tuple[str, ...]
    external_verifier: str
    digest: str = ""

    def __post_init__(self) -> None:
        _text(self.task_id, "task_id")
        _text(self.run_id, "run_id")
        if not isinstance(self.status, Phase5Status):
            raise ValueError("receipt status is invalid")
        object.__setattr__(self, "graph", _strings(self.graph, "graph"))
        if self.graph != FIXED_GRAPH:
            raise ValueError("receipt graph is not the fixed Phase 5 graph")
        for name in ("events", "artifact_versions", "stale_evidence"):
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        for name in (
            "builder_invocations",
            "verifier_invocations",
            "critic_invocations",
            "repair_invocations",
        ):
            _integer(getattr(self, name), name)
        if self.repair_invocations > 1:
            raise ValueError("receipt exceeds the repair budget")
        _text(self.external_verifier, "external_verifier", maximum=512)
        digest = self.digest or digest_payload(
            {
                "task_id": self.task_id,
                "run_id": self.run_id,
                "status": self.status,
                "graph": self.graph,
                "events": self.events,
                "builder_invocations": self.builder_invocations,
                "verifier_invocations": self.verifier_invocations,
                "critic_invocations": self.critic_invocations,
                "repair_invocations": self.repair_invocations,
                "artifact_versions": self.artifact_versions,
                "stale_evidence": self.stale_evidence,
                "external_verifier": self.external_verifier,
            }
        )
        _digest(digest, "digest")
        object.__setattr__(self, "digest", digest)


def public_data(value: Any) -> Any:
    """Serialize frozen Phase 5 records without exposing arbitrary objects."""

    if isinstance(value, Phase5Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: public_data(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): public_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [public_data(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def canonical_json(value: object) -> str:
    return json.dumps(public_data(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
