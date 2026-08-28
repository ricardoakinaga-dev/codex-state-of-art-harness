"""Deterministic, data-only task classification primitives."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum

from .models import (
    BlastRadius,
    ClassificationTrace,
    Complexity,
    Confidence,
    DataImpact,
    EvidenceSummary,
    ParallelismPotential,
    Provenance,
    RecordEnvelope,
    RecordStatus,
    RepositoryClassification,
    RepositoryContext,
    ResearchNeed,
    Reversibility,
    Risk,
    SchemaVersion,
    SecurityImpact,
    SourceType,
    TaskDomain,
    TaskProfile,
    TrustState,
    UserImpact,
    VisualImportance,
)

DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"
_TOKEN_PATTERN = re.compile(r"[A-Za-zÀ-ÿ0-9]+(?:[-'][A-Za-zÀ-ÿ0-9]+)*")


@dataclass(frozen=True, slots=True)
class TaskRequest:
    """Immutable input envelope for classification from an unstructured goal."""

    objective: str
    requested_outcome: str = ""
    task_id: str = "TASK-UNCLASSIFIED"
    run_id: str = "RUN-UNCLASSIFIED"
    constraints: tuple[str, ...] = ()
    non_goals: tuple[str, ...] = ()
    repository_context: RepositoryContext = field(
        default_factory=lambda: RepositoryContext(
            root=None,
            classification=RepositoryClassification.UNKNOWN,
            trust_state=TrustState.UNKNOWN,
        )
    )
    evidence_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    created_at: str = DEFAULT_TIMESTAMP
    source_type: SourceType = SourceType.USER_PROVIDED
    hints: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class DimensionAssessment:
    """Reason/evidence attached to one normalized classification dimension."""

    dimension: str
    value: object
    reason: str
    confidence: Confidence
    evidence_refs: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()

    @property
    def value_name(self) -> str:
        return str(getattr(self.value, "value", self.value))


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """A profile plus per-axis explanations for callers that need the trace."""

    profile: TaskProfile
    assessments: tuple[DimensionAssessment, ...]

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return self.profile.classification_trace.rule_ids

    @property
    def unresolved(self) -> tuple[str, ...]:
        return self.profile.classification_trace.unresolved


def _tuple_strings(values: Iterable[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError("classification collections must contain strings")
        cleaned = value.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _enum[EnumT: Enum](enum_type: type[EnumT], value: object) -> EnumT:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError:
            try:
                return enum_type[value.upper()]
            except KeyError as exc:
                raise ValueError(f"invalid {enum_type.__name__}: {value!r}") from exc
    raise TypeError(f"expected {enum_type.__name__} or string")


def _assessment_value[EnumT: Enum](
    assessment: DimensionAssessment, enum_type: type[EnumT]
) -> EnumT:
    value = assessment.value
    if not isinstance(value, enum_type):
        raise TypeError(
            f"{assessment.dimension} assessment must contain {enum_type.__name__}, "
            f"got {type(value).__name__}"
        )
    return value


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _tokens(value: str) -> frozenset[str]:
    return frozenset(item.casefold() for item in _TOKEN_PATTERN.findall(value))


def _has(tokens: frozenset[str], *values: str) -> bool:
    return any(value.casefold() in tokens for value in values)


def _phrase(text: str, *values: str) -> bool:
    folded = text.casefold()
    return any(value.casefold() in folded for value in values)


def _is_local_presentation_edit(text: str) -> bool:
    """Recognize focused copy/UI edits before scoring incidental nouns."""

    tokens = _tokens(text)
    edit_verbs = {
        "change",
        "correct",
        "edit",
        "fix",
        "modify",
        "replace",
        "rename",
        "set",
        "update",
        "alter",
        "mudar",
        "corrigir",
        "editar",
        "atualizar",
    }
    direct_markers = {
        "css",
        "margin",
        "readme",
        "typo",
        "spelling",
        "whitespace",
        "ortografia",
    }
    label_markers = {"caption", "copy", "label", "text", "title", "wording"}
    return bool(
        tokens.intersection(direct_markers)
        or (tokens.intersection(edit_verbs) and tokens.intersection(label_markers))
    )


def _is_visual_probe(text: str) -> bool:
    """Separate a small visual question from research synthesis work."""

    tokens = _tokens(text)
    query_markers = {"research", "investigate", "question", "pesquisa", "investigar"}
    visual_markers = {
        "appearance",
        "button",
        "card",
        "color",
        "colour",
        "layout",
        "visual",
    }
    broad_research = {
        "alternatives",
        "benchmark",
        "comparison",
        "compare",
        "current",
        "deep",
        "latest",
        "literature",
        "market",
        "options",
        "sources",
        "survey",
        "systematic",
    }
    return bool(
        tokens.intersection(query_markers)
        and tokens.intersection(visual_markers)
        and not tokens.intersection(broad_research)
    )


def _choose(
    dimension: str,
    value: object,
    reason: str,
    rule_ids: Iterable[str],
    *,
    evidence_refs: tuple[str, ...],
    confidence: Confidence,
    assumptions: tuple[str, ...] = (),
    unresolved: tuple[str, ...] = (),
) -> DimensionAssessment:
    return DimensionAssessment(
        dimension=dimension,
        value=value,
        reason=reason,
        confidence=confidence,
        evidence_refs=evidence_refs,
        rule_ids=_dedupe(rule_ids),
        assumptions=assumptions,
        unresolved=unresolved,
    )


def _hint(hints: Mapping[str, object], name: str) -> object | None:
    return hints.get(name) or hints.get(name.upper())


def _domain_assessment(
    text: str, hints: Mapping[str, object], evidence: tuple[str, ...], confidence: Confidence
) -> DimensionAssessment:
    explicit = _hint(hints, "domain")
    if explicit is not None:
        value = _enum(TaskDomain, explicit)
        return _choose(
            "domain",
            value,
            "domain was supplied explicitly",
            (f"CLS-DOMAIN-{_value(value)}",),
            evidence_refs=evidence,
            confidence=Confidence.HIGH,
        )
    tokens = _tokens(text)
    if _is_local_presentation_edit(text):
        value = TaskDomain.DOCUMENTATION if _has(tokens, "readme") else TaskDomain.FRONTEND
        return _choose(
            "domain",
            value,
            "focused presentation edit takes precedence over incidental surface nouns",
            (f"CLS-DOMAIN-{_value(value)}-FOCUSED-EDIT",),
            evidence_refs=evidence,
            confidence=confidence,
        )
    if _is_visual_probe(text):
        return _choose(
            "domain",
            TaskDomain.DESIGN,
            "a small visual question is not research synthesis",
            ("CLS-DOMAIN-DESIGN-VISUAL-PROBE",),
            evidence_refs=evidence,
            confidence=confidence,
        )
    groups: tuple[tuple[TaskDomain, tuple[str, ...]], ...] = (
        (
            TaskDomain.SECURITY,
            (
                "security",
                "auth",
                "authentication",
                "authorization",
                "secret",
                "credential",
                "password",
                "csrf",
                "xss",
                "vulnerability",
                "threat",
                "segurança",
                "credencial",
            ),
        ),
        (
            TaskDomain.RESEARCH,
            (
                "research",
                "investigate",
                "compare",
                "comparison",
                "sources",
                "survey",
                "current",
                "latest",
                "pesquisa",
                "investigar",
                "comparar",
                "atual",
            ),
        ),
        (
            TaskDomain.API,
            (
                "api",
                "endpoint",
                "rest",
                "graphql",
                "http",
                "pagination",
                "request",
                "response",
                "rota",
            ),
        ),
        (
            TaskDomain.DATA,
            (
                "database",
                "schema",
                "sql",
                "migration",
                "migrate",
                "dataset",
                "etl",
                "data",
                "banco",
                "migração",
                "migrar",
            ),
        ),
        (
            TaskDomain.FRONTEND,
            (
                "frontend",
                "front-end",
                "ui",
                "component",
                "css",
                "html",
                "react",
                "responsive",
                "accessibility",
                "browser",
                "interface",
                "button",
                "margin",
            ),
        ),
        (
            TaskDomain.DESIGN,
            (
                "design",
                "visual",
                "landing",
                "illustration",
                "image",
                "banner",
                "brand",
                "sprite",
                "layout",
                "card",
                "color",
                "colour",
                "blue",
                "imagem",
                "visual",
            ),
        ),
        (
            TaskDomain.GAME,
            ("game", "gameplay", "sprite", "physics", "collision", "level", "jogo", "colisão"),
        ),
        (
            TaskDomain.INFRASTRUCTURE,
            (
                "deploy",
                "docker",
                "kubernetes",
                "k8s",
                "ci",
                "cd",
                "systemd",
                "proxy",
                "infrastructure",
                "infraestrutura",
            ),
        ),
        (
            TaskDomain.DOCUMENTATION,
            ("docs", "documentation", "readme", "guide", "tutorial", "adr", "documentação"),
        ),
        (
            TaskDomain.CONTENT,
            (
                "article",
                "newsletter",
                "social",
                "post",
                "thread",
                "copy",
                "script",
                "carousel",
                "conteúdo",
            ),
        ),
        (
            TaskDomain.OPERATIONS,
            ("incident", "monitor", "on-call", "runbook", "operations", "production", "operação"),
        ),
        (
            TaskDomain.INTEGRATION,
            ("integrate", "integration", "provider", "mcp", "oauth", "webhook", "integração"),
        ),
        (TaskDomain.BACKEND, ("backend", "back-end", "server", "service", "worker", "queue")),
        (
            TaskDomain.ENGINEERING,
            (
                "code",
                "implement",
                "fix",
                "refactor",
                "feature",
                "function",
                "bug",
                "test",
                "validate",
                "contract",
                "código",
                "corrigir",
            ),
        ),
    )
    scores = {domain: sum(token in tokens for token in words) for domain, words in groups}
    ranked = sorted(
        scores.items(),
        key=lambda item: (
            -item[1],
            groups.index(next(group for group in groups if group[0] is item[0])),
        ),
    )
    top, second = ranked[0], ranked[1]
    if top[1] == 0:
        return _choose(
            "domain",
            TaskDomain.GENERAL,
            "no domain boundary is evidenced by the request",
            ("CLS-DOMAIN-GENERAL",),
            evidence_refs=evidence,
            confidence=Confidence.LOW,
            unresolved=("DOMAIN_AMBIGUOUS",),
        )
    if top[1] == second[1] and top[1] > 0:
        pair = {top[0], second[0]}
        if pair == {TaskDomain.API, TaskDomain.BACKEND}:
            value = TaskDomain.API
            reason = "API is the narrower public boundary than backend implementation"
        else:
            value = TaskDomain.MIXED
            reason = (
                "multiple domain boundaries have equal lexical evidence: "
                f"{_value(top[0])}, {_value(second[0])}"
            )
        return _choose(
            "domain",
            value,
            reason,
            ("CLS-DOMAIN-MIXED",),
            evidence_refs=evidence,
            confidence=confidence,
            unresolved=("DOMAIN_AMBIGUOUS",) if value is TaskDomain.MIXED else (),
        )
    value = top[0]
    matched_words = sorted(
        word for word in _tokens(text) if word in {token for _, words in groups for token in words}
    )
    return _choose(
        "domain",
        value,
        f"matched domain signals: {', '.join(matched_words)}",
        (f"CLS-DOMAIN-{_value(value)}",),
        evidence_refs=evidence,
        confidence=confidence,
    )


def _complexity_assessment(
    text: str,
    hints: Mapping[str, object],
    evidence: tuple[str, ...],
    confidence: Confidence,
    risk: Risk,
    reversibility: Reversibility,
) -> DimensionAssessment:
    explicit = _hint(hints, "complexity")
    if explicit is not None:
        value = _enum(Complexity, explicit)
        return _choose(
            "complexity",
            value,
            "complexity was supplied explicitly",
            (f"CLS-COMPLEXITY-{_value(value)}",),
            evidence_refs=evidence,
            confidence=Confidence.HIGH,
        )
    tokens = _tokens(text)
    critical = _has(
        tokens,
        "migration",
        "migrate",
        "irreversible",
        "production",
        "delete",
        "drop",
        "destroy",
        "financial",
        "regulatory",
        "credential",
        "secret",
        "migração",
        "apagar",
        "irreversível",
    )
    large = (
        _has(
            tokens,
            "architecture",
            "system",
            "multi",
            "multiple",
            "several",
            "service",
            "refactor",
            "comprehensive",
            "end-to-end",
            "cross-system",
            "multi-service",
            "sistema",
        )
        or text.count(" and ") >= 2
    )
    medium = _has(
        tokens,
        "endpoint",
        "feature",
        "integration",
        "api",
        "database",
        "tests",
        "verification",
        "component",
        "several",
        "vários",
    ) and not _is_local_presentation_edit(text)
    trivial = _has(
        tokens,
        "typo",
        "rename",
        "label",
        "formatting",
        "whitespace",
        "css",
        "margin",
        "ortografia",
    ) or _is_local_presentation_edit(text)
    trivial = trivial and not (large or critical)
    if critical or risk is Risk.CRITICAL or reversibility is Reversibility.IRREVERSIBLE:
        value, rule = Complexity.CRITICAL, "CLS-COMPLEXITY-CRITICAL"
        reason = "risk or irreversibility sets the critical complexity floor"
    elif large:
        value, rule, reason = (
            Complexity.LARGE,
            "CLS-COMPLEXITY-LARGE",
            "multiple boundaries or architectural scope are present",
        )
    elif medium:
        value, rule, reason = (
            Complexity.MEDIUM,
            "CLS-COMPLEXITY-MEDIUM",
            "the request contains more than one related responsibility",
        )
    elif trivial:
        value, rule, reason = (
            Complexity.TRIVIAL,
            "CLS-COMPLEXITY-TRIVIAL",
            "the request is a single local reversible edit",
        )
    else:
        value, rule, reason = (
            Complexity.SMALL,
            "CLS-COMPLEXITY-SMALL",
            "the request has one bounded responsibility",
        )
    return _choose(
        "complexity", value, reason, (rule,), evidence_refs=evidence, confidence=confidence
    )


def _risk_assessment(
    text: str, hints: Mapping[str, object], evidence: tuple[str, ...], confidence: Confidence
) -> DimensionAssessment:
    explicit = _hint(hints, "risk")
    if explicit is not None:
        value = _enum(Risk, explicit)
        return _choose(
            "risk",
            value,
            "risk was supplied explicitly",
            (f"CLS-RISK-{_value(value)}",),
            evidence_refs=evidence,
            confidence=Confidence.HIGH,
        )
    tokens = _tokens(text)
    if _is_local_presentation_edit(text) or _is_visual_probe(text):
        value, reason = Risk.LOW, "the request is a focused local presentation change"
    elif _has(
        tokens,
        "irreversible",
        "destroy",
        "drop",
        "delete",
        "production",
        "financial",
        "regulatory",
        "safety",
        "medical",
        "credential",
        "secret",
        "migrate",
        "migration",
        "irreversível",
        "apagar",
    ):
        value, reason = (
            Risk.CRITICAL,
            "destructive, production, credential or irreversible signals "
            "require the critical floor",
        )
    elif _has(
        tokens,
        "security",
        "auth",
        "authentication",
        "authorization",
        "public",
        "deploy",
        "provider",
        "network",
        "customer",
        "broad",
        "segurança",
        "público",
    ):
        value, reason = (
            Risk.HIGH,
            "security, public-surface or external-system signals raise plausible harm",
        )
    elif _has(
        tokens,
        "api",
        "endpoint",
        "database",
        "persistent",
        "write",
        "save",
        "integration",
        "service",
        "server",
        "data",
        "dados",
    ):
        value, reason = Risk.MEDIUM, "a service, API or persistent-data boundary is involved"
    elif _has(
        tokens,
        "typo",
        "read-only",
        "readonly",
        "local",
        "validate",
        "test",
        "docs",
        "documentation",
        "sem execução",
        "label",
        "rename",
        "css",
        "margin",
        "icon",
        "formatting",
        "whitespace",
    ):
        value, reason = Risk.LOW, "the request is local/read-only or a focused check"
    else:
        value, reason = Risk.UNKNOWN, "the request does not establish a consequence boundary"
    unresolved = ("RISK_UNKNOWN",) if value is Risk.UNKNOWN else ()
    return _choose(
        "risk",
        value,
        reason,
        (f"CLS-RISK-{_value(value)}",),
        evidence_refs=evidence,
        confidence=confidence if value is not Risk.UNKNOWN else Confidence.UNKNOWN,
        unresolved=unresolved,
    )


def _security_assessment(
    text: str, hints: Mapping[str, object], evidence: tuple[str, ...], confidence: Confidence
) -> DimensionAssessment:
    explicit = _hint(hints, "security_impact")
    if explicit is not None:
        value = _enum(SecurityImpact, explicit)
        return _choose(
            "security_impact",
            value,
            "security impact was supplied explicitly",
            (f"CLS-SECURITY-{_value(value)}",),
            evidence_refs=evidence,
            confidence=Confidence.HIGH,
        )
    tokens = _tokens(text)
    if _is_local_presentation_edit(text) or _is_visual_probe(text):
        value, reason = (
            SecurityImpact.NONE,
            "surface wording or visual intent is not a security boundary",
        )
    elif _has(
        tokens,
        "secret",
        "credential",
        "password",
        "private",
        "exploit",
        "rce",
        "drop",
        "credentials",
        "credencial",
        "segredo",
    ):
        value, reason = (
            SecurityImpact.CRITICAL,
            "credential, secret or exploit handling is a critical security boundary",
        )
    elif _has(
        tokens,
        "security",
        "auth",
        "authentication",
        "authorization",
        "csrf",
        "xss",
        "permission",
        "privilege",
        "network",
        "public",
        "oauth",
        "segurança",
    ):
        value, reason = (
            SecurityImpact.HIGH,
            "authentication, authorization, input, network or public access is in scope",
        )
    elif _has(tokens, "provider", "integration", "api", "endpoint", "server"):
        value, reason = (
            SecurityImpact.MEDIUM,
            "an external or service boundary needs security consideration",
        )
    elif _has(tokens, "code", "implement", "fix", "refactor", "test", "validate", "contract"):
        value, reason = (
            SecurityImpact.LOW,
            "code or contract changes have a bounded security review surface",
        )
    else:
        value, reason = SecurityImpact.NONE, "no security-sensitive boundary is evidenced"
    return _choose(
        "security_impact",
        value,
        reason,
        (f"CLS-SECURITY-{_value(value)}",),
        evidence_refs=evidence,
        confidence=confidence,
    )


def _data_assessment(
    text: str, hints: Mapping[str, object], evidence: tuple[str, ...], confidence: Confidence
) -> DimensionAssessment:
    explicit = _hint(hints, "data_impact")
    if explicit is not None:
        value = _enum(DataImpact, explicit)
        return _choose(
            "data_impact",
            value,
            "data impact was supplied explicitly",
            (f"CLS-DATA-{_value(value)}",),
            evidence_refs=evidence,
            confidence=Confidence.HIGH,
        )
    tokens = _tokens(text)
    if _has(
        tokens,
        "migration",
        "migrate",
        "schema",
        "drop",
        "delete",
        "database",
        "banco",
        "migração",
        "migrar",
    ):
        value, reason = (
            DataImpact.MIGRATION,
            "schema, database or migration language implies structural data change",
        )
    elif _has(
        tokens,
        "pii",
        "sensitive",
        "personal",
        "private",
        "secret",
        "credential",
        "expose",
        "sensitive",
        "sensível",
    ):
        value, reason = DataImpact.SENSITIVE, "sensitive or private data is named"
    elif _has(
        tokens,
        "persistent",
        "persist",
        "save",
        "store",
        "write",
        "update",
        "create",
        "endpoint",
        "database",
        "dados",
    ):
        value, reason = DataImpact.PERSISTENT, "the request writes or serves persistent data"
    elif _has(
        tokens,
        "local",
        "repository",
        "workspace",
        "file",
        "read-only",
        "validate",
        "manifest",
        "contract",
    ):
        value, reason = DataImpact.LOCAL, "data is constrained to local/project inspection"
    else:
        value, reason = DataImpact.NONE, "no data read/write or exposure boundary is evidenced"
    return _choose(
        "data_impact",
        value,
        reason,
        (f"CLS-DATA-{_value(value)}",),
        evidence_refs=evidence,
        confidence=confidence,
    )


def _visual_assessment(
    text: str, hints: Mapping[str, object], evidence: tuple[str, ...], confidence: Confidence
) -> DimensionAssessment:
    explicit = _hint(hints, "visual_importance")
    if explicit is not None:
        value = _enum(VisualImportance, explicit)
        return _choose(
            "visual_importance",
            value,
            "visual importance was supplied explicitly",
            (f"CLS-VISUAL-{_value(value)}",),
            evidence_refs=evidence,
            confidence=Confidence.HIGH,
        )
    tokens = _tokens(text)
    if _is_local_presentation_edit(text):
        value, reason = (
            VisualImportance.SUPPORTING,
            "the request changes presentation without making visual fidelity "
            "the primary deliverable",
        )
    elif _is_visual_probe(text) or _has(
        tokens,
        "high-fidelity",
        "pixel",
        "pixel-perfect",
        "landing",
        "hero",
        "image",
        "illustration",
        "banner",
        "brand",
        "card",
        "color",
        "colour",
        "blue",
        "secure-looking",
        "visual",
        "sprite",
        "imagem",
    ):
        value, reason = (
            VisualImportance.PRIMARY,
            "the requested outcome depends on visual pixels or fidelity",
        )
    elif _has(
        tokens,
        "ui",
        "frontend",
        "component",
        "css",
        "html",
        "responsive",
        "render",
        "screenshot",
        "accessibility",
        "interface",
    ):
        value, reason = (
            VisualImportance.MATERIAL,
            "a user interface or rendered state is part of the outcome",
        )
    elif _has(tokens, "label", "icon", "format", "readme"):
        value, reason = (
            VisualImportance.SUPPORTING,
            "visual presentation supports a primarily non-visual outcome",
        )
    else:
        value, reason = (
            VisualImportance.NONE,
            "no pixels, interaction or visual fidelity is in scope",
        )
    return _choose(
        "visual_importance",
        value,
        reason,
        (f"CLS-VISUAL-{_value(value)}",),
        evidence_refs=evidence,
        confidence=confidence,
    )


def _research_assessment(
    text: str, hints: Mapping[str, object], evidence: tuple[str, ...], confidence: Confidence
) -> DimensionAssessment:
    explicit = _hint(hints, "research_need")
    if explicit is not None:
        value = _enum(ResearchNeed, explicit)
        return _choose(
            "research_need",
            value,
            "research need was supplied explicitly",
            (f"CLS-RESEARCH-{_value(value)}",),
            evidence_refs=evidence,
            confidence=Confidence.HIGH,
        )
    tokens = _tokens(text)
    if _is_visual_probe(text):
        value, reason = ResearchNeed.NONE, "a visual question does not require research synthesis"
    elif _has(tokens, "deep", "market", "sizing", "literature", "systematic", "profunda"):
        value, reason = ResearchNeed.DEEP, "the request asks for broad or deep synthesis"
    elif _has(tokens, "compare", "comparison", "alternatives", "options", "benchmark", "comparar"):
        value, reason = ResearchNeed.COMPARATIVE, "multiple options or a benchmark must be compared"
    elif _has(
        tokens, "current", "latest", "today", "recent", "version", "up-to-date", "atual", "recente"
    ):
        value, reason = (
            ResearchNeed.FRESHNESS_REQUIRED,
            "the answer depends on current or versioned facts",
        )
    else:
        value, reason = (
            ResearchNeed.NONE,
            "no freshness, comparison or research deliverable is evidenced",
        )
    return _choose(
        "research_need",
        value,
        reason,
        (f"CLS-RESEARCH-{_value(value)}",),
        evidence_refs=evidence,
        confidence=confidence,
    )


def _parallel_assessment(
    text: str, hints: Mapping[str, object], evidence: tuple[str, ...], confidence: Confidence
) -> DimensionAssessment:
    explicit = _hint(hints, "parallelism_potential")
    if explicit is not None:
        value = _enum(ParallelismPotential, explicit)
        return _choose(
            "parallelism_potential",
            value,
            "parallelism was supplied explicitly",
            (f"CLS-PARALLEL-{_value(value)}",),
            evidence_refs=evidence,
            confidence=Confidence.HIGH,
        )
    tokens = _tokens(text)
    if _has(
        tokens, "independent", "independently", "parallel", "lanes", "workstreams", "fan-out"
    ) and (
        _has(tokens, "two", "three", "multiple", "several", "lanes", "workstreams")
        or " and " in text.casefold()
    ):
        value, reason = ParallelismPotential.HIGH, "independent lanes are explicitly described"
    elif _has(tokens, "independent", "parallel", "possible", "separate", "lanes"):
        value, reason = (
            ParallelismPotential.MEDIUM,
            "some independent work may exist, but delegation benefit needs proof",
        )
    elif _has(tokens, "api", "endpoint", "tests", "verification", "report"):
        value, reason = (
            ParallelismPotential.LOW,
            "a small bounded task may separate checks without requiring orchestration",
        )
    else:
        value, reason = ParallelismPotential.NONE, "no independently verifiable lane is evidenced"
    unresolved = (
        ("PARALLELISM_UNPROVEN",)
        if value in (ParallelismPotential.MEDIUM, ParallelismPotential.HIGH)
        else ()
    )
    return _choose(
        "parallelism_potential",
        value,
        reason,
        (f"CLS-PARALLEL-{_value(value)}",),
        evidence_refs=evidence,
        confidence=confidence,
        unresolved=unresolved,
    )


def _reversibility_assessment(
    text: str, hints: Mapping[str, object], evidence: tuple[str, ...], confidence: Confidence
) -> DimensionAssessment:
    explicit = _hint(hints, "reversibility")
    if explicit is not None:
        value = _enum(Reversibility, explicit)
        return _choose(
            "reversibility",
            value,
            "reversibility was supplied explicitly",
            (f"CLS-REVERSIBILITY-{_value(value)}",),
            evidence_refs=evidence,
            confidence=Confidence.HIGH,
        )
    tokens = _tokens(text)
    if _has(
        tokens,
        "irreversible",
        "destroy",
        "drop",
        "delete",
        "migrate",
        "migration",
        "irreversível",
        "apagar",
    ):
        value, reason = (
            Reversibility.IRREVERSIBLE,
            "destructive or irreversible language is explicit",
        )
    elif _has(
        tokens, "deploy", "production", "auth", "security", "refactor", "provider", "network"
    ):
        value, reason = (
            Reversibility.HARD,
            "the change crosses a boundary that is costly to undo safely",
        )
    elif _has(tokens, "write", "save", "store", "update", "create", "persistent", "integration"):
        value, reason = (
            Reversibility.CONTROLLED,
            "side effects may be reversed only through controlled state",
        )
    else:
        value, reason = (
            Reversibility.EASY,
            "the request is local, read-only or otherwise easy to undo",
        )
    return _choose(
        "reversibility",
        value,
        reason,
        (f"CLS-REVERSIBILITY-{_value(value)}",),
        evidence_refs=evidence,
        confidence=confidence,
    )


def _blast_assessment(
    text: str, hints: Mapping[str, object], evidence: tuple[str, ...], confidence: Confidence
) -> DimensionAssessment:
    explicit = _hint(hints, "blast_radius")
    if explicit is not None:
        value = _enum(BlastRadius, explicit)
        return _choose(
            "blast_radius",
            value,
            "blast radius was supplied explicitly",
            (f"CLS-BLAST-{_value(value)}",),
            evidence_refs=evidence,
            confidence=Confidence.HIGH,
        )
    tokens = _tokens(text)
    if _is_local_presentation_edit(text) or _is_visual_probe(text):
        value, reason = BlastRadius.LOCAL, "the request is a bounded local presentation change"
    elif _has(
        tokens,
        "cross-system",
        "cross",
        "multi-service",
        "system",
        "deploy",
        "provider",
        "mcp",
        "infraestrutura",
    ):
        value, reason = (
            BlastRadius.CROSS_SYSTEM,
            "multiple systems or an external boundary may be affected",
        )
    elif _has(tokens, "public", "internet", "customer", "all", "release", "público"):
        value, reason = BlastRadius.PUBLIC, "the request names a public or released surface"
    elif _has(tokens, "product", "user-facing", "users", "customer", "broad", "produto"):
        value, reason = BlastRadius.PRODUCT, "a product-level user flow is in scope"
    elif _has(tokens, "api", "endpoint", "backend", "server", "database", "service"):
        value, reason = BlastRadius.SERVICE, "a service boundary is in scope"
    elif _has(tokens, "module", "component", "function", "file", "local", "manifest", "contract"):
        value, reason = BlastRadius.MODULE, "the request is bounded to a module or component"
    elif _has(
        tokens,
        "read-only",
        "readonly",
        "validate",
        "typo",
        "docs",
        "label",
        "rename",
        "css",
        "margin",
        "icon",
        "formatting",
        "whitespace",
    ):
        value, reason = (
            BlastRadius.LOCAL,
            "the request is a local read-only or documentation change",
        )
    else:
        value, reason = BlastRadius.UNKNOWN, "the request does not identify an affected surface"
    unresolved = ("BLAST_RADIUS_UNKNOWN",) if value is BlastRadius.UNKNOWN else ()
    return _choose(
        "blast_radius",
        value,
        reason,
        (f"CLS-BLAST-{_value(value)}",),
        evidence_refs=evidence,
        confidence=confidence if value is not BlastRadius.UNKNOWN else Confidence.UNKNOWN,
        unresolved=unresolved,
    )


def _user_assessment(
    text: str, hints: Mapping[str, object], evidence: tuple[str, ...], confidence: Confidence
) -> DimensionAssessment:
    explicit = _hint(hints, "user_impact")
    if explicit is not None:
        value = _enum(UserImpact, explicit)
        return _choose(
            "user_impact",
            value,
            "user impact was supplied explicitly",
            (f"CLS-USER-{_value(value)}",),
            evidence_refs=evidence,
            confidence=Confidence.HIGH,
        )
    tokens = _tokens(text)
    if _has(
        tokens, "safety", "medical", "life-critical", "financial", "regulatory", "safety-relevant"
    ):
        value, reason = (
            UserImpact.SAFETY_RELEVANT,
            "failure could affect safety, regulated or financial outcomes",
        )
    elif _has(tokens, "public", "customer", "customers", "all", "broad", "users", "internet"):
        value, reason = UserImpact.BROAD, "the request targets many users or a public audience"
    elif _has(tokens, "user", "team", "client", "limited"):
        value, reason = UserImpact.LIMITED, "the request names a bounded user group"
    else:
        value, reason = UserImpact.INTERNAL, "no external user population is evidenced"
    return _choose(
        "user_impact",
        value,
        reason,
        (f"CLS-USER-{_value(value)}",),
        evidence_refs=evidence,
        confidence=confidence,
    )


def _overall_confidence(
    assessments: tuple[DimensionAssessment, ...],
    evidence: tuple[str, ...],
    unresolved: tuple[str, ...],
    explicit: object | None,
) -> Confidence:
    if explicit is not None:
        return _enum(Confidence, explicit)
    if any(item.value is Risk.UNKNOWN or item.value is BlastRadius.UNKNOWN for item in assessments):
        return Confidence.UNKNOWN
    if unresolved:
        return Confidence.LOW if evidence else Confidence.UNKNOWN
    return Confidence.HIGH if evidence else Confidence.LOW


def _request_from_input(
    objective: str | TaskRequest | TaskProfile | Mapping[str, object],
    requested_outcome: str,
    *,
    task_id: str,
    run_id: str,
    constraints: Iterable[str],
    non_goals: Iterable[str],
    repository_context: RepositoryContext | None,
    evidence_refs: Iterable[str],
    source_refs: Iterable[str],
    assumptions: Iterable[str],
    created_at: str | None,
    source_type: SourceType | str,
    hints: Mapping[str, object] | None,
    overrides: Mapping[str, object],
) -> TaskRequest | TaskProfile:
    if isinstance(objective, TaskProfile):
        return normalize_task_profile(objective)
    if isinstance(objective, TaskRequest):
        return objective
    if isinstance(objective, Mapping):
        data = objective
        if "schema_version" in data:
            from .serialization import from_dict

            parsed = from_dict(data, TaskProfile)
            return normalize_task_profile(parsed)
        objective = str(data.get("objective", ""))
        requested_outcome = str(data.get("requested_outcome", requested_outcome))
    if not isinstance(objective, str):
        raise TypeError("objective must be a string, TaskRequest or TaskProfile")
    merged_hints = dict(hints or {})
    merged_hints.update(overrides)
    return TaskRequest(
        objective=objective,
        requested_outcome=requested_outcome,
        task_id=task_id,
        run_id=run_id,
        constraints=_tuple_strings(constraints),
        non_goals=_tuple_strings(non_goals),
        repository_context=repository_context
        or RepositoryContext(None, RepositoryClassification.UNKNOWN, TrustState.UNKNOWN),
        evidence_refs=_tuple_strings(evidence_refs),
        source_refs=_tuple_strings(source_refs),
        assumptions=_tuple_strings(assumptions),
        created_at=created_at or DEFAULT_TIMESTAMP,
        source_type=_enum(SourceType, source_type),
        hints=tuple(sorted(merged_hints.items())),
    )


def _build_profile(request: TaskRequest) -> tuple[TaskProfile, tuple[DimensionAssessment, ...]]:
    if not request.objective.strip():
        raise ValueError("objective must be non-empty")
    text = " ".join((request.objective, request.requested_outcome, *request.constraints))
    evidence = tuple(request.evidence_refs)
    hints = dict(request.hints)
    assumptions = tuple(request.assumptions)
    seed_confidence = Confidence.HIGH if evidence else Confidence.LOW

    risk = _risk_assessment(text, hints, evidence, seed_confidence)
    reversibility = _reversibility_assessment(text, hints, evidence, seed_confidence)
    risk_value = _assessment_value(risk, Risk)
    reversibility_value = _assessment_value(reversibility, Reversibility)
    assessments = (
        _domain_assessment(text, hints, evidence, seed_confidence),
        _complexity_assessment(
            text, hints, evidence, seed_confidence, risk_value, reversibility_value
        ),
        risk,
        _security_assessment(text, hints, evidence, seed_confidence),
        _data_assessment(text, hints, evidence, seed_confidence),
        _user_assessment(text, hints, evidence, seed_confidence),
        _visual_assessment(text, hints, evidence, seed_confidence),
        _research_assessment(text, hints, evidence, seed_confidence),
        _parallel_assessment(text, hints, evidence, seed_confidence),
        reversibility,
        _blast_assessment(text, hints, evidence, seed_confidence),
    )
    unresolved = list(item for assessment in assessments for item in assessment.unresolved)
    if not evidence:
        unresolved.append("EVIDENCE_UNAVAILABLE")
    unresolved_tuple = _dedupe(unresolved)
    explicit_confidence = _hint(hints, "confidence")
    overall = _overall_confidence(assessments, evidence, unresolved_tuple, explicit_confidence)
    if overall is Confidence.UNKNOWN and "CLASSIFICATION_UNCERTAIN" not in unresolved_tuple:
        unresolved_tuple = unresolved_tuple + ("CLASSIFICATION_UNCERTAIN",)
    rule_ids = _dedupe(item for assessment in assessments for item in assessment.rule_ids)
    trace_assumptions = _dedupe(
        (*assumptions, "lexical signals are treated as observations, not execution authority")
    )
    if not request.repository_context.root:
        trace_assumptions = _dedupe((*trace_assumptions, "repository boundary was not supplied"))
    created_at = request.created_at or DEFAULT_TIMESTAMP
    domain = _assessment_value(assessments[0], TaskDomain)
    complexity = _assessment_value(assessments[1], Complexity)
    security_impact = _assessment_value(assessments[3], SecurityImpact)
    data_impact = _assessment_value(assessments[4], DataImpact)
    user_impact = _assessment_value(assessments[5], UserImpact)
    visual_importance = _assessment_value(assessments[6], VisualImportance)
    research_need = _assessment_value(assessments[7], ResearchNeed)
    parallelism_potential = _assessment_value(assessments[8], ParallelismPotential)
    blast_radius = _assessment_value(assessments[10], BlastRadius)
    profile = TaskProfile(
        schema_version=SchemaVersion.TASK_PROFILE,
        task_id=request.task_id,
        run_id=request.run_id,
        record=RecordEnvelope(
            status=RecordStatus.CURRENT,
            provenance=Provenance(request.source_type, request.source_refs, created_at),
            evidence_refs=evidence,
        ),
        objective=request.objective.strip(),
        requested_outcome=request.requested_outcome.strip() or "classified task profile",
        domain=domain,
        complexity=complexity,
        risk=risk_value,
        security_impact=security_impact,
        data_impact=data_impact,
        user_impact=user_impact,
        visual_importance=visual_importance,
        research_need=research_need,
        parallelism_potential=parallelism_potential,
        reversibility=reversibility_value,
        blast_radius=blast_radius,
        confidence=overall,
        constraints=request.constraints,
        non_goals=request.non_goals,
        repository_context=request.repository_context,
        evidence=EvidenceSummary(evidence, overall),
        classification_trace=ClassificationTrace(rule_ids, trace_assumptions, unresolved_tuple),
        created_at=created_at,
    )
    return profile, assessments


def classify_with_trace(
    objective: str | TaskRequest | TaskProfile | Mapping[str, object],
    requested_outcome: str = "",
    *,
    task_id: str = "TASK-UNCLASSIFIED",
    run_id: str = "RUN-UNCLASSIFIED",
    constraints: Iterable[str] = (),
    non_goals: Iterable[str] = (),
    repository_context: RepositoryContext | None = None,
    evidence_refs: Iterable[str] = (),
    source_refs: Iterable[str] = (),
    assumptions: Iterable[str] = (),
    created_at: str | None = None,
    source_type: SourceType | str = SourceType.USER_PROVIDED,
    hints: Mapping[str, object] | None = None,
    **overrides: object,
) -> ClassificationResult:
    request = _request_from_input(
        objective,
        requested_outcome,
        task_id=task_id,
        run_id=run_id,
        constraints=constraints,
        non_goals=non_goals,
        repository_context=repository_context,
        evidence_refs=evidence_refs,
        source_refs=source_refs,
        assumptions=assumptions,
        created_at=created_at,
        source_type=source_type,
        hints=hints,
        overrides=overrides,
    )
    if isinstance(request, TaskProfile):
        return ClassificationResult(request, explain_classification(request))
    profile, assessments = _build_profile(request)
    return ClassificationResult(profile, assessments)


def classify_task(
    objective: str | TaskRequest | TaskProfile | Mapping[str, object],
    requested_outcome: str = "",
    *,
    task_id: str = "TASK-UNCLASSIFIED",
    run_id: str = "RUN-UNCLASSIFIED",
    constraints: Iterable[str] = (),
    non_goals: Iterable[str] = (),
    repository_context: RepositoryContext | None = None,
    evidence_refs: Iterable[str] = (),
    source_refs: Iterable[str] = (),
    assumptions: Iterable[str] = (),
    created_at: str | None = None,
    source_type: SourceType | str = SourceType.USER_PROVIDED,
    hints: Mapping[str, object] | None = None,
    **kwargs: object,
) -> TaskProfile:
    """Classify a goal into a valid immutable ``TaskProfile``."""

    return classify_with_trace(
        objective,
        requested_outcome,
        task_id=task_id,
        run_id=run_id,
        constraints=constraints,
        non_goals=non_goals,
        repository_context=repository_context,
        evidence_refs=evidence_refs,
        source_refs=source_refs,
        assumptions=assumptions,
        created_at=created_at,
        source_type=source_type,
        hints=hints,
        **kwargs,
    ).profile


def normalize_task_profile(profile: TaskProfile | Mapping[str, object]) -> TaskProfile:
    """Return a canonical enum/tuple copy while preserving assumptions and evidence."""

    if isinstance(profile, Mapping):
        from .serialization import from_dict

        profile = from_dict(profile, TaskProfile)
    if not isinstance(profile, TaskProfile):
        raise TypeError("profile must be a TaskProfile or contract mapping")
    record_provenance = replace(
        profile.record.provenance,
        source_type=_enum(SourceType, profile.record.provenance.source_type),
        source_refs=tuple(profile.record.provenance.source_refs),
    )
    normalized = replace(
        profile,
        schema_version=_enum(SchemaVersion, profile.schema_version),
        record=replace(
            profile.record,
            status=_enum(RecordStatus, profile.record.status),
            provenance=record_provenance,
            evidence_refs=tuple(profile.record.evidence_refs),
        ),
        domain=_enum(TaskDomain, profile.domain),
        complexity=_enum(Complexity, profile.complexity),
        risk=_enum(Risk, profile.risk),
        visual_importance=_enum(VisualImportance, profile.visual_importance),
        security_impact=_enum(SecurityImpact, profile.security_impact),
        data_impact=_enum(DataImpact, profile.data_impact),
        user_impact=_enum(UserImpact, profile.user_impact),
        blast_radius=_enum(BlastRadius, profile.blast_radius),
        research_need=_enum(ResearchNeed, profile.research_need),
        parallelism_potential=_enum(ParallelismPotential, profile.parallelism_potential),
        reversibility=_enum(Reversibility, profile.reversibility),
        confidence=_enum(Confidence, profile.confidence),
        constraints=tuple(profile.constraints),
        non_goals=tuple(profile.non_goals),
        repository_context=replace(
            profile.repository_context,
            classification=_enum(
                RepositoryClassification, profile.repository_context.classification
            ),
            trust_state=_enum(TrustState, profile.repository_context.trust_state),
        ),
        evidence=replace(
            profile.evidence,
            refs=tuple(profile.evidence.refs),
            confidence=_enum(Confidence, profile.evidence.confidence),
        ),
        classification_trace=replace(
            profile.classification_trace,
            rule_ids=tuple(profile.classification_trace.rule_ids),
            assumptions=tuple(profile.classification_trace.assumptions),
            unresolved=tuple(profile.classification_trace.unresolved),
        ),
    )
    return normalized


def explain_classification(
    profile: TaskProfile | ClassificationResult,
) -> tuple[DimensionAssessment, ...]:
    """Expose deterministic explanations for a profile's ten-plus axes."""

    if isinstance(profile, ClassificationResult):
        return profile.assessments
    normalized = normalize_task_profile(profile)
    values = (
        ("domain", normalized.domain),
        ("complexity", normalized.complexity),
        ("risk", normalized.risk),
        ("security_impact", normalized.security_impact),
        ("data_impact", normalized.data_impact),
        ("user_impact", normalized.user_impact),
        ("visual_importance", normalized.visual_importance),
        ("research_need", normalized.research_need),
        ("parallelism_potential", normalized.parallelism_potential),
        ("reversibility", normalized.reversibility),
        ("blast_radius", normalized.blast_radius),
    )
    rule_ids = normalized.classification_trace.rule_ids
    unresolved = normalized.classification_trace.unresolved
    return tuple(
        _choose(
            dimension,
            value,
            f"{dimension} is normalized as {_value(value)} and preserved from the profile",
            rule_ids or (f"CLS-{dimension.upper()}-{_value(value)}",),
            evidence_refs=normalized.evidence.refs,
            confidence=normalized.confidence,
            assumptions=normalized.classification_trace.assumptions,
            unresolved=unresolved,
        )
        for dimension, value in values
    )


normalize = normalize_task_profile
classify = classify_task
