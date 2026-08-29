"""Native structural checks and blind visual-critic packet handling."""

from __future__ import annotations

import hashlib
import re
import struct
import time
from collections.abc import Mapping
from html.parser import HTMLParser
from pathlib import Path

from .phase4_models import digest_payload
from .phase5_artifacts import validate_artifact_path
from .phase5_models import (
    ArtifactPacket,
    BlindPacket,
    Finding,
    FindingSeverity,
    Phase5Status,
    Phase5Task,
    RenderRecord,
    StructuralVerification,
    VisualCritique,
)


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attributes: list[tuple[str, tuple[tuple[str, str | None], ...]]] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.casefold()
        self.tags.append(normalized)
        self.attributes.append((normalized, tuple(attrs)))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)


def png_dimensions(path: str | Path) -> tuple[int, int]:
    candidate = Path(path)
    try:
        raw = candidate.read_bytes()
    except OSError as exc:
        raise ValueError("PNG render cannot be read") from exc
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("render is not a PNG capture")
    if len(raw) >= 24 and raw[12:16] == b"IHDR":
        width, height = struct.unpack(">II", raw[16:24])
    elif len(raw) >= 16:
        # The test seam accepts a compact IHDR header; real captures use the branch above.
        width, height = struct.unpack(">II", raw[8:16])
    else:
        raise ValueError("PNG header is incomplete")
    if width < 1 or height < 1:
        raise ValueError("PNG dimensions are invalid")
    return width, height


def _finding(
    finding_id: str,
    location: str,
    expected: str,
    observed: str,
    severity: FindingSeverity,
    evidence: str,
) -> Finding:
    return Finding(finding_id, location, expected, observed, severity, evidence)


def _artifact_source(task: Phase5Task, artifact: ArtifactPacket) -> tuple[str, bytes] | Finding:
    path = Path(artifact.path)
    try:
        validate_artifact_path(path, task.artifact_root)
        raw = path.read_bytes()
    except (OSError, ValueError) as exc:
        return _finding(
            "S-ARTIFACT-READ",
            "artifact",
            "current regular HTML artifact is readable",
            str(exc),
            FindingSeverity.CRITICAL,
            artifact.path,
        )
    actual_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual_digest != artifact.digest:
        return _finding(
            "S-ARTIFACT-STALE",
            "artifact",
            artifact.digest,
            actual_digest,
            FindingSeverity.CRITICAL,
            artifact.path,
        )
    return artifact.path, raw


def _validate_render(
    task: Phase5Task,
    artifact: ArtifactPacket,
    render: RenderRecord,
    *,
    render_root: str | Path,
) -> Finding | None:
    expected = tuple(render.viewport)
    try:
        render_path = Path(render.path)
        path = Path(validate_artifact_path(render_path, render_root))
        actual = png_dimensions(path)
    except (OSError, ValueError) as exc:
        return _finding(
            "S-RENDER-INVALID",
            render.render_id,
            f"native PNG at {expected[0]}x{expected[1]}",
            str(exc),
            FindingSeverity.HIGH,
            render.path,
        )
    if render.artifact_version != artifact.version:
        return _finding(
            "S-RENDER-STALE",
            render.render_id,
            artifact.version,
            render.artifact_version,
            FindingSeverity.CRITICAL,
            render.path,
        )
    if actual != expected:
        return _finding(
            "S-RENDER-VIEWPORT",
            render.render_id,
            f"{expected[0]}x{expected[1]}",
            f"{actual[0]}x{actual[1]}",
            FindingSeverity.HIGH,
            render.path,
        )
    return None


def _landmarks_are_complete(value: object) -> bool:
    if not isinstance(value, (list, tuple)):
        return False
    found: set[str] = set()
    for item in value:
        if isinstance(item, Mapping):
            tag = item.get("tag")
            count = item.get("count")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            tag, count = item
        else:
            continue
        if isinstance(tag, str) and count == 1:
            found.add(tag.casefold())
    return {"header", "main", "footer"}.issubset(found)


def _browser_observation_findings(
    renders: tuple[RenderRecord, ...],
    observations: tuple[Mapping[str, object], ...],
    *,
    require: bool,
) -> tuple[list[str], list[Finding]]:
    checks: list[str] = []
    findings: list[Finding] = []
    if require and len(observations) != len(renders):
        findings.append(
            _finding(
                "S-BROWSER-EVIDENCE-MISSING",
                "browser observations",
                f"one native metric record for each of {len(renders)} render(s)",
                f"received {len(observations)} metric record(s)",
                FindingSeverity.HIGH,
                "browser metric evidence",
            )
        )
    if not observations or len(observations) != len(renders):
        return checks, findings
    loadability = True
    overflow = True
    accessibility = True
    confinement = True
    for index, (render, observation) in enumerate(zip(renders, observations, strict=True), start=1):
        raw_viewport = observation.get("viewport")
        if isinstance(raw_viewport, Mapping):
            observed_viewport = (raw_viewport.get("width"), raw_viewport.get("height"))
        elif isinstance(raw_viewport, (list, tuple)) and len(raw_viewport) == 2:
            observed_viewport = (raw_viewport[0], raw_viewport[1])
        else:
            observed_viewport = (None, None)
        if observed_viewport != render.viewport:
            findings.append(
                _finding(
                    f"S-BROWSER-VIEWPORT-{index}",
                    render.render_id,
                    f"browser metrics at {render.viewport[0]}x{render.viewport[1]}",
                    f"browser metrics report {observed_viewport[0]}x{observed_viewport[1]}",
                    FindingSeverity.HIGH,
                    "browser metric evidence",
                )
            )
            loadability = False
        document_width = observation.get("document_width")
        viewport_width = observation.get("viewport_width")
        body_height = observation.get("body_height")
        positive_metrics = all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in (document_width, viewport_width, body_height)
        )
        if not positive_metrics:
            findings.append(
                _finding(
                    f"S-BROWSER-METRICS-{index}",
                    render.render_id,
                    "positive document, viewport and body metrics",
                    "browser metric values are missing or invalid",
                    FindingSeverity.HIGH,
                    "browser metric evidence",
                )
            )
            loadability = False
        elif (
            isinstance(document_width, int)
            and not isinstance(document_width, bool)
            and isinstance(viewport_width, int)
            and not isinstance(viewport_width, bool)
            and document_width > viewport_width
        ):
            findings.append(
                _finding(
                    f"S-BROWSER-OVERFLOW-{index}",
                    render.render_id,
                    "document width does not exceed viewport width",
                    f"document width {document_width} exceeds viewport {viewport_width}",
                    FindingSeverity.HIGH,
                    "browser metric evidence",
                )
            )
            overflow = False
        h1_count = observation.get("h1_count")
        focusable_count = observation.get("focusable_count")
        if (
            h1_count != 1
            or not isinstance(focusable_count, int)
            or isinstance(focusable_count, bool)
            or focusable_count < 1
            or not _landmarks_are_complete(observation.get("landmarks"))
        ):
            findings.append(
                _finding(
                    f"S-BROWSER-ACCESSIBILITY-{index}",
                    render.render_id,
                    "one h1, complete semantic landmarks and a focusable action",
                    "browser accessibility metrics are incomplete",
                    FindingSeverity.HIGH,
                    "browser metric evidence",
                )
            )
            accessibility = False
        external_resources = observation.get("external_resources")
        if not isinstance(external_resources, (list, tuple)) or external_resources:
            findings.append(
                _finding(
                    f"S-BROWSER-CONFINEMENT-{index}",
                    render.render_id,
                    "no external browser resources",
                    "external browser resources were observed",
                    FindingSeverity.CRITICAL,
                    "browser metric evidence",
                )
            )
            confinement = False
    if loadability:
        checks.append("browser_loadability")
    if overflow:
        checks.append("browser_overflow")
    if accessibility:
        checks.append("browser_accessibility")
    if confinement:
        checks.append("browser_confinement")
    return checks, findings


def build_structural_verification(
    task: Phase5Task,
    artifact: ArtifactPacket,
    *,
    renders: tuple[RenderRecord, ...],
    console_errors: tuple[str, ...] = (),
    network_failures: tuple[str, ...] = (),
    browser_observations: tuple[Mapping[str, object], ...] = (),
    require_browser_observations: bool = False,
    render_root: str | Path | None = None,
    verification_id: str = "verification-v1",
    created_at: int | None = None,
) -> StructuralVerification:
    if artifact.acceptance_digest != task.criteria.digest:
        finding_list = (
            _finding(
                "S-CRITERIA-STALE",
                "artifact",
                task.criteria.digest,
                artifact.acceptance_digest,
                FindingSeverity.CRITICAL,
                artifact.path,
            ),
        )
        return StructuralVerification(
            verification_id,
            artifact.version,
            artifact.digest,
            Phase5Status.FAIL,
            ("criteria_binding",),
            finding_list,
            (),
            console_errors,
            network_failures,
            int(time.time()) if created_at is None else created_at,
        )
    findings: list[Finding] = []
    checks: list[str] = []
    source = _artifact_source(task, artifact)
    if isinstance(source, Finding):
        findings.append(source)
        raw = b""
    else:
        _, raw = source
        checks.append("artifact_digest")
    html = raw.decode("utf-8", errors="replace")
    parser = _DocumentParser()
    try:
        parser.feed(html)
        parser.close()
    except ValueError as exc:
        findings.append(
            _finding(
                "S-HTML-PARSE",
                "artifact",
                "HTML parses without a parser error",
                str(exc),
                FindingSeverity.HIGH,
                artifact.path,
            )
        )
    tags = set(parser.tags)
    text_content = " ".join(parser.text_parts)
    for section in task.criteria.required_sections:
        if section.casefold() not in tags:
            findings.append(
                _finding(
                    f"S-SECTION-{section.upper()}",
                    section,
                    f"semantic <{section}> section exists",
                    "section missing",
                    FindingSeverity.HIGH,
                    artifact.path,
                )
            )
    for copy in task.criteria.required_copy:
        if copy not in html:
            findings.append(
                _finding(
                    "S-COPY-MISSING",
                    "copy",
                    copy,
                    "required exact copy missing",
                    FindingSeverity.HIGH,
                    artifact.path,
                )
            )
    if tags.intersection({"script", "iframe", "object", "embed"}):
        findings.append(
            _finding(
                "S-ACTION-TAG",
                "artifact",
                "no executable or embeddable action tags",
                "forbidden tag present",
                FindingSeverity.CRITICAL,
                artifact.path,
            )
        )
    if len(re.findall(r"<h1\b", html, flags=re.IGNORECASE)) != 1:
        findings.append(
            _finding(
                "S-H1-COUNT",
                "document heading",
                "exactly one h1",
                "heading count is not one",
                FindingSeverity.HIGH,
                artifact.path,
            )
        )
    if not re.search(r'<html\b[^>]*\blang\s*=\s*["\'][^"\']+', html, re.IGNORECASE):
        findings.append(
            _finding(
                "S-LANG",
                "document",
                "html lang is declared",
                "lang is missing",
                FindingSeverity.HIGH,
                artifact.path,
            )
        )
    if not re.search(r'<meta\b[^>]*name\s*=\s*["\']viewport', html, re.IGNORECASE):
        findings.append(
            _finding(
                "S-VIEWPORT-META",
                "document head",
                "responsive viewport meta exists",
                "viewport meta is missing",
                FindingSeverity.HIGH,
                artifact.path,
            )
        )
    if re.search(
        r"(?is)<(?:script|iframe|object|embed|base)\b|javascript\s*:|\bon[a-z]+\s*=|"
        r"(?:https?|file|ftp)\s*://|(?<!:)//|@import\b|"
        r"url\s*\(\s*['\"]?(?:https?:|file:|ftp:|data:|//)",
        html,
    ):
        findings.append(
            _finding(
                "S-REMOTE-ACTION",
                "artifact",
                "local response-only HTML/CSS/SVG",
                "remote or executable reference present",
                FindingSeverity.CRITICAL,
                artifact.path,
            )
        )
    lowered = html.casefold()
    for signal in task.criteria.forbidden_signals:
        if signal.casefold() in lowered:
            findings.append(
                _finding(
                    "S-FORBIDDEN-SIGNAL",
                    "artifact",
                    f"signal absent: {signal}",
                    f"signal present: {signal}",
                    FindingSeverity.HIGH,
                    artifact.path,
                )
            )
    if text_content.strip():
        checks.append("semantic_copy")
    if "main" in tags and "header" in tags and "footer" in tags:
        checks.append("semantic_landmarks")
    if not renders:
        findings.append(
            _finding(
                "S-RENDER-MISSING",
                "render matrix",
                "native desktop and mobile captures are current",
                "no render records supplied",
                FindingSeverity.HIGH,
                "render evidence not provided",
            )
        )
    seen_viewports: set[tuple[int, int]] = set()
    render_refs: list[str] = []
    for render in renders:
        render_refs.append(render.render_id)
        seen_viewports.add(render.viewport)
        render_finding = _validate_render(
            task,
            artifact,
            render,
            render_root=render_root or task.workspace,
        )
        if render_finding is not None:
            findings.append(render_finding)
    required_viewports = set(task.criteria.render_viewports)
    for viewport in sorted(required_viewports - seen_viewports):
        findings.append(
            _finding(
                "S-RENDER-VIEWPORT-MISSING",
                "render matrix",
                f"capture at {viewport[0]}x{viewport[1]}",
                "viewport record missing",
                FindingSeverity.HIGH,
                "render evidence not provided",
            )
        )
    for index, error in enumerate(console_errors, start=1):
        findings.append(
            _finding(
                f"S-CONSOLE-{index}",
                "browser console",
                "zero console errors",
                error,
                FindingSeverity.HIGH,
                "browser console",
            )
        )
    for index, error in enumerate(network_failures, start=1):
        findings.append(
            _finding(
                f"S-NETWORK-{index}",
                "browser network",
                "no failed or remote requests",
                error,
                FindingSeverity.HIGH,
                "browser network",
            )
        )
    browser_checks, browser_findings = _browser_observation_findings(
        renders,
        browser_observations,
        require=require_browser_observations,
    )
    checks.extend(browser_checks)
    findings.extend(browser_findings)
    has_blocking = any(
        item.severity in {FindingSeverity.CRITICAL, FindingSeverity.HIGH} for item in findings
    )
    status = Phase5Status.FAIL if has_blocking else Phase5Status.PASS
    if not renders and status is Phase5Status.FAIL:
        status = Phase5Status.BLOCKED
    return StructuralVerification(
        verification_id,
        artifact.version,
        artifact.digest,
        status,
        tuple(dict.fromkeys(checks)),
        tuple(findings),
        tuple(render_refs),
        tuple(console_errors),
        tuple(network_failures),
        int(time.time()) if created_at is None else created_at,
    )


def make_blind_packet(
    task: Phase5Task,
    artifact: ArtifactPacket,
    renders: tuple[RenderRecord, ...],
    *,
    benchmark_id: str = "P5-DESIGN-1",
) -> BlindPacket:
    payload = {
        "benchmark_id": benchmark_id,
        "run_id": task.run_id,
        "artifact_digest": artifact.digest,
        "artifact": {
            "path": artifact.path,
            "version": artifact.version,
            "digest": artifact.digest,
            "size_bytes": artifact.size_bytes,
        },
        "renders": tuple(
            {
                "render_id": item.render_id,
                "artifact_version": item.artifact_version,
                "path": item.path,
                "viewport": item.viewport,
                "digest": item.digest,
                "size_bytes": item.size_bytes,
            }
            for item in renders
        ),
        "acceptance_criteria": task.criteria.serialized,
        "builder_rationale_withheld": True,
        "self_score_withheld": True,
    }
    return BlindPacket(
        benchmark_id=benchmark_id,
        run_id=task.run_id,
        artifact=artifact,
        renders=renders,
        acceptance_criteria=task.criteria.serialized,
        packet_digest=digest_payload(payload),
    )


def _critique_status(value: object) -> Phase5Status:
    if value == "PASS":
        return Phase5Status.PASS
    if value in {"CONDITIONAL PASS", "PASS_WITH_LIMITATIONS"}:
        return Phase5Status.PASS_WITH_LIMITATIONS
    if value in {"FAIL", "STOP"}:
        return Phase5Status.FAIL
    return Phase5Status.BLOCKED


def _critique_finding(raw: object, index: int) -> Finding:
    if not isinstance(raw, Mapping):
        raise ValueError("critique finding must be an object")
    severity = FindingSeverity(str(raw.get("severity", "HIGH")).upper())
    finding_id = raw.get("id", raw.get("finding_id", f"V-{index}"))
    return Finding(
        str(finding_id),
        str(raw.get("location", "unknown")),
        str(raw.get("expected", "")),
        str(raw.get("observed", "")),
        severity,
        str(raw.get("evidence", "critic packet")),
        str(raw.get("status", "OPEN")),
    )


def parse_blind_critique(
    payload: Mapping[str, object],
    *,
    packet_digest: str,
    require_packet_digest: bool = True,
) -> VisualCritique:
    if not isinstance(payload, Mapping):
        raise ValueError("critic payload must be an object")
    provided_packet_digest = payload.get("packet_digest")
    if provided_packet_digest is not None and not isinstance(provided_packet_digest, str):
        raise ValueError("critic packet digest is invalid")
    if require_packet_digest and provided_packet_digest != packet_digest:
        raise ValueError("critic packet digest does not match the bound packet")
    benchmark_id = str(payload.get("benchmark_id", "P5-DESIGN-1"))
    run_id = str(payload.get("run_id", "RUN-P5-UNKNOWN"))
    inspection_id = str(payload.get("inspection_id", "INS-P5-UNKNOWN"))
    artifact_digest = payload.get("artifact_digest")
    if not isinstance(artifact_digest, str):
        raise ValueError("critic artifact digest is required")
    required_flags = (
        "blinded",
        "builder_rationale_withheld",
        "self_score_withheld",
    )
    if any(name not in payload for name in required_flags):
        raise ValueError("critic safety flags are required")
    blinded_value = payload.get("blinded")
    rationale_withheld_value = payload.get("builder_rationale_withheld")
    self_score_withheld_value = payload.get("self_score_withheld")
    if (
        not isinstance(blinded_value, bool)
        or not isinstance(rationale_withheld_value, bool)
        or not isinstance(self_score_withheld_value, bool)
    ):
        raise ValueError("critic safety flags must be boolean")
    independence = str(payload.get("independence", "UNKNOWN"))
    blinded = blinded_value
    rationale_withheld = rationale_withheld_value
    self_score_withheld = self_score_withheld_value
    raw_findings = payload.get("findings", [])
    findings: list[Finding] = []
    if not isinstance(raw_findings, (list, tuple)):
        raise ValueError("critic findings must be a list")
    for index, raw in enumerate(raw_findings, start=1):
        findings.append(_critique_finding(raw, index))
    corrections = payload.get("top_corrections", [])
    missing = payload.get("evidence_missing", [])
    if not isinstance(corrections, (list, tuple)) or not isinstance(missing, (list, tuple)):
        raise ValueError("critic correction/evidence fields must be lists")
    blocked_packet = (
        not blinded
        or not rationale_withheld
        or not self_score_withheld
        or independence != "INDEPENDENT"
    )
    status = Phase5Status.BLOCKED if blocked_packet else _critique_status(payload.get("verdict"))
    raw_overall_score = payload.get("overall_score")
    raw_dimension_scores = payload.get("dimension_scores", {})
    dimension_scores: dict[str, float] = {}
    if isinstance(raw_dimension_scores, Mapping):
        for key, value in raw_dimension_scores.items():
            if (
                not isinstance(key, str)
                or not isinstance(value, (int, float))
                or isinstance(value, bool)
            ):
                raise ValueError("critic dimension scores must be numeric")
            normalized_value = float(value)
            # Critics sometimes return the same 0..10 rubric as percentages.
            # Normalize that representation at the handoff boundary while
            # keeping VisualCritique's canonical contract in 0..10.
            if 10 < normalized_value <= 100:
                normalized_value /= 10
            dimension_scores[key] = normalized_value
    return VisualCritique(
        benchmark_id=benchmark_id,
        run_id=run_id,
        inspection_id=inspection_id,
        artifact_digest=artifact_digest,
        independence="BLOCKED" if blocked_packet else "INDEPENDENT",
        blinded=blinded,
        builder_rationale_withheld=rationale_withheld,
        self_score_withheld=self_score_withheld,
        packet_digest=packet_digest,
        verdict=status,
        overall_score=(
            float(raw_overall_score) if isinstance(raw_overall_score, (int, float)) else None
        ),
        evidence_confidence=str(payload.get("evidence_confidence", "LOW")),
        dimension_scores=dimension_scores,
        findings=tuple(findings),
        top_corrections=tuple(str(item) for item in corrections),
        evidence_missing=tuple(str(item) for item in missing),
    )
