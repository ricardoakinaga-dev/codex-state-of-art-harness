"""Versioned browser-boundary finalization for the Phase 5 pilot."""

from __future__ import annotations

import argparse
import json
import re
import stat
import time
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

from .phase4_evidence import EvidenceWriter
from .phase5_artifacts import validate_artifact_path
from .phase5_models import (
    FIXED_GRAPH,
    ArtifactPacket,
    AssuranceReport,
    CompositionReceipt,
    FindingSeverity,
    Phase5Status,
    Phase5Task,
    RenderRecord,
    StructuralVerification,
    VisualCritique,
)
from .phase5_paths import (
    Phase5CliError,
)
from .phase5_paths import (
    evidence_path as _evidence_path,
)
from .phase5_paths import (
    safe_project_path as _safe_project_path,
)
from .phase5_paths import (
    task_path as _task_path,
)
from .phase5_pilot import load_task, read_json_mapping, write_public_json
from .phase5_verification import (
    build_structural_verification,
    make_blind_packet,
    parse_blind_critique,
)


def _read_string_list(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise Phase5CliError("observation input must be a regular file")
        if metadata.st_size > 64 * 1024:
            raise Phase5CliError("observation input exceeds its bound")
        value = json.loads(path.read_text(encoding="utf-8"))
    except Phase5CliError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Phase5CliError("observation input cannot be read safely") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise Phase5CliError("observation input must be a list of strings")
    return tuple(value)


def version_suffix(version: str) -> str:
    if version not in {"artifact_v1", "artifact_v2"}:
        raise Phase5CliError("artifact version is invalid")
    return version.rsplit("_v", maxsplit=1)[1]


def validate_receipt_binding(
    task: Phase5Task,
    receipt: Mapping[str, object],
    *,
    eligibility: Mapping[str, object],
    authorization: Mapping[str, object],
    context: Mapping[str, object],
) -> dict[str, str]:
    """Require the artifact receipt to inherit the exact preflight identity."""

    fingerprint = eligibility.get("fingerprint")
    if eligibility.get("status") != Phase5Status.PASS or not isinstance(fingerprint, Mapping):
        raise Phase5CliError("builder eligibility is not a passing exact identity")
    expected_values = {
        "capability_id": fingerprint.get("capability_id"),
        "capability_version": fingerprint.get("version"),
        "package_fingerprint": fingerprint.get("package_fingerprint"),
        "manifest_fingerprint": fingerprint.get("manifest_fingerprint"),
        "authorization_id": authorization.get("authorization_id"),
        "context_digest": context.get("digest"),
    }
    if any(not isinstance(value, str) or not value for value in expected_values.values()):
        raise Phase5CliError("builder identity evidence is incomplete")
    expected = cast(dict[str, str], expected_values)
    if (
        authorization.get("task_id") != task.task_id
        or authorization.get("run_id") != task.run_id
        or authorization.get("capability_id") != expected["capability_id"]
        or authorization.get("capability_version") != expected["capability_version"]
        or authorization.get("package_fingerprint") != expected["package_fingerprint"]
    ):
        raise Phase5CliError("builder authorization is not bound to the eligible package")
    if (
        context.get("task_id") != task.task_id
        or context.get("capability_id") != expected["capability_id"]
        or context.get("package_fingerprint") != expected["package_fingerprint"]
        or context.get("digest") != expected["context_digest"]
    ):
        raise Phase5CliError("builder context is not bound to the eligible package")
    for name, value in expected.items():
        if receipt.get(name) != value:
            raise Phase5CliError(f"builder receipt {name} is not bound to preflight")
    return expected


def artifact_from_receipt(
    task: Phase5Task,
    receipt: dict[str, object],
    *,
    version: str = "artifact_v1",
    expected_identity: Mapping[str, str] | None = None,
) -> ArtifactPacket:
    version_suffix(version)
    if expected_identity is not None:
        for name, value in expected_identity.items():
            if receipt.get(name) != value:
                raise Phase5CliError(f"builder receipt {name} is not bound")
    if receipt.get("task_id") != task.task_id or receipt.get("run_id") != task.run_id:
        raise Phase5CliError("builder receipt is bound to a different task or run")
    if receipt.get("producer_capability") != "design-director":
        raise Phase5CliError("builder receipt producer is not design-director")
    if receipt.get("status") != "PASS":
        raise Phase5CliError("builder receipt is not a successful invocation receipt")
    if receipt.get("artifact_version") != version:
        raise Phase5CliError(
            "builder receipt artifact version does not match the requested version"
        )
    path_value = receipt.get("artifact_path")
    invocation_value = receipt.get("attempts")
    artifact_id_value = receipt.get("artifact_id")
    attempt_count = receipt.get("attempt_count")
    if not isinstance(path_value, str) or not isinstance(invocation_value, list):
        raise Phase5CliError("builder receipt does not bind an artifact")
    if not invocation_value:
        raise Phase5CliError("builder receipt has no invocation attempts")
    if not isinstance(artifact_id_value, str) or not artifact_id_value:
        raise Phase5CliError("builder receipt artifact id is invalid")
    if not isinstance(attempt_count, int) or isinstance(attempt_count, bool):
        raise Phase5CliError("builder receipt attempt count is invalid")
    if attempt_count != len(invocation_value):
        raise Phase5CliError("builder receipt attempt count is not bound to its attempts")
    artifact_path = validate_artifact_path(path_value, task.workspace)
    if Path(artifact_path).name != "index.html" or Path(artifact_path).parent.name != version:
        raise Phase5CliError("builder receipt artifact path is not version-bound")
    try:
        html = Path(artifact_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise Phase5CliError("artifact cannot be read") from exc
    for attempt in invocation_value:
        if not isinstance(attempt, Mapping) or not isinstance(attempt.get("invocation_id"), str):
            raise Phase5CliError("builder receipt invocation binding is invalid")
    last_attempt = invocation_value[-1]
    assert isinstance(last_attempt, Mapping)
    parent_artifact_digest: str | None = None
    if version == "artifact_v2":
        raw_parent_digest = receipt.get("parent_artifact_digest")
        if not isinstance(raw_parent_digest, str):
            raise Phase5CliError("repair receipt does not bind its parent artifact")
        parent_artifact_digest = raw_parent_digest
    artifact = ArtifactPacket.from_content(
        artifact_id=artifact_id_value,
        version=version,
        path=artifact_path,
        content=html,
        producer_capability="design-director",
        invocation_id=last_attempt["invocation_id"],
        task=task,
        parent_artifact_digest=parent_artifact_digest,
    )
    if receipt.get("artifact_digest") != artifact.digest:
        raise Phase5CliError("artifact digest does not match the builder receipt")
    if version == "artifact_v2" and artifact.parent_artifact_digest is None:
        raise Phase5CliError("repair receipt does not bind its parent artifact")
    return artifact


def render_records(
    project_root: Path,
    evidence_root: Path,
    desktop: Path,
    mobile: Path,
    *,
    artifact_version: str = "artifact_v1",
) -> tuple[RenderRecord, ...]:
    suffix = version_suffix(artifact_version)
    desktop_path = _safe_project_path(project_root, desktop, "desktop render", must_exist=True)
    mobile_path = _safe_project_path(project_root, mobile, "mobile render", must_exist=True)
    if not desktop_path.is_relative_to(evidence_root) or not mobile_path.is_relative_to(
        evidence_root
    ):
        raise Phase5CliError("renders must remain inside the evidence directory")
    return (
        RenderRecord.from_file(
            f"render-desktop-v{suffix}",
            artifact_version,
            desktop_path,
            (1440, 900),
            root=evidence_root,
            captured_at=int(time.time()),
        ),
        RenderRecord.from_file(
            f"render-mobile-v{suffix}",
            artifact_version,
            mobile_path,
            (390, 844),
            root=evidence_root,
            captured_at=int(time.time()),
        ),
    )


def needs_repair(critique: VisualCritique) -> bool:
    return any(
        item.status == "OPEN"
        and item.severity
        in {FindingSeverity.CRITICAL, FindingSeverity.HIGH, FindingSeverity.MEDIUM}
        for item in critique.findings
    )


def _browser_metrics(
    project_root: Path,
    evidence_root: Path,
    renders: tuple[RenderRecord, ...],
    *,
    artifact: ArtifactPacket,
) -> tuple[Mapping[str, object], ...]:
    observations: list[Mapping[str, object]] = []
    for render in renders:
        render_path = Path(render.path)
        metric_candidate = render_path.with_name(f"{render_path.stem}-metrics.json")
        metric_path = _safe_project_path(
            project_root, metric_candidate, "browser metrics", must_exist=True
        )
        if not metric_path.is_relative_to(evidence_root):
            raise Phase5CliError("browser metrics must remain inside the evidence directory")
        observation = read_json_mapping(metric_path)
        if observation.get("artifact_version") != artifact.version:
            raise Phase5CliError("browser metrics are bound to a different artifact version")
        if observation.get("artifact_digest") != artifact.digest:
            raise Phase5CliError("browser metrics are not bound to the current artifact")
        if observation.get("capture_method") != "playwright_native":
            raise Phase5CliError("browser metrics are not native capture evidence")
        url = observation.get("url")
        if not isinstance(url, str) or not url.startswith("http://127.0.0.1:"):
            raise Phase5CliError("browser metrics are missing their captured URL")
        viewport = observation.get("viewport")
        if (
            not isinstance(viewport, Mapping)
            or viewport.get("width") != render.viewport[0]
            or viewport.get("height") != render.viewport[1]
        ):
            raise Phase5CliError("browser metrics viewport is not bound to the render")
        browser = observation.get("browser")
        executable_digest = (
            browser.get("executable_digest") if isinstance(browser, Mapping) else None
        )
        if (
            not isinstance(browser, Mapping)
            or not isinstance(browser.get("engine"), str)
            or not isinstance(browser.get("version"), str)
            or not isinstance(browser.get("executable"), str)
            or not isinstance(executable_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", executable_digest) is None
            or not isinstance(observation.get("capture_id"), str)
        ):
            raise Phase5CliError("browser metrics lack native executable provenance")
        observations.append(observation)
    return tuple(observations)


def _receipt_identity(
    evidence_root: Path,
    task: Phase5Task,
    version: str,
    receipt: Mapping[str, object],
) -> dict[str, str]:
    authorization_name = (
        "builder-authorization.json"
        if version == "artifact_v1"
        else "builder-repair-authorization.json"
    )
    context_name = (
        "builder-context-manifest.json"
        if version == "artifact_v1"
        else "builder-repair-context-manifest.json"
    )
    return validate_receipt_binding(
        task,
        receipt,
        eligibility=read_json_mapping(evidence_root / "eligibility.json"),
        authorization=read_json_mapping(evidence_root / authorization_name),
        context=read_json_mapping(evidence_root / context_name),
    )


def _summary_markdown(
    task: Phase5Task,
    artifact: ArtifactPacket,
    renders: tuple[RenderRecord, ...],
    structural: StructuralVerification,
    critique: VisualCritique,
    assurance: AssuranceReport,
    composition: CompositionReceipt,
) -> str:
    return "\n".join(
        (
            "# Phase 5 design-director pilot",
            "",
            f"Task: {task.task_id}",
            f"Artifact: {artifact.version} ({artifact.digest})",
            f"Renders: {', '.join(item.path for item in renders)}",
            f"Structural verification: {structural.status.value}",
            f"Visual critique: {critique.verdict.value} ({critique.independence})",
            f"Assurance: {assurance.status.value}, support {assurance.support_level}",
            f"Composition receipt: {composition.digest}",
            "",
            "Limitations: external verification-loop was ineligible; "
            "host load remains unobservable.",
        )
    )


def finalize(root: Path, arguments: argparse.Namespace) -> dict[str, object]:
    task = load_task(_task_path(root, arguments.task), project_root=root)
    evidence_root = _evidence_path(root, arguments.evidence_dir)
    writer = EvidenceWriter(evidence_root)
    version = getattr(arguments, "artifact_version", "artifact_v1")
    suffix = version_suffix(version)
    receipt_name = (
        "builder-invocation-receipt.json"
        if version == "artifact_v1"
        else "builder-repair-receipt.json"
    )
    receipt = cast(
        dict[str, object],
        dict(read_json_mapping(evidence_root / receipt_name)),
    )
    identity = _receipt_identity(evidence_root, task, version, receipt)
    artifact = artifact_from_receipt(
        task,
        receipt,
        version=version,
        expected_identity=identity,
    )
    renders = render_records(
        root,
        evidence_root,
        arguments.desktop,
        arguments.mobile,
        artifact_version=version,
    )
    browser_observations = _browser_metrics(
        root,
        evidence_root,
        renders,
        artifact=artifact,
    )
    console_path = (
        _safe_project_path(root, arguments.console_errors, "console observations", must_exist=True)
        if arguments.console_errors is not None
        else None
    )
    network_path = (
        _safe_project_path(
            root, arguments.network_failures, "network observations", must_exist=True
        )
        if arguments.network_failures is not None
        else None
    )
    critique_path = _safe_project_path(root, arguments.critique, "critic packet", must_exist=True)
    structural = build_structural_verification(
        task,
        artifact,
        renders=renders,
        console_errors=_read_string_list(console_path),
        network_failures=_read_string_list(network_path),
        browser_observations=browser_observations,
        require_browser_observations=True,
        render_root=evidence_root,
        verification_id=f"VER-P5-V{suffix}",
    )
    packet = make_blind_packet(task, artifact, renders)
    critique_raw = read_json_mapping(critique_path)
    for name, expected in (
        ("benchmark_id", packet.benchmark_id),
        ("run_id", packet.run_id),
        ("packet_digest", packet.packet_digest),
    ):
        if critique_raw.get(name) != expected:
            raise Phase5CliError(f"critic {name} does not match the bound packet")
    if critique_raw.get("artifact_digest") != artifact.digest:
        raise Phase5CliError(f"critic packet artifact digest does not match {version}")
    try:
        critique = parse_blind_critique(
            critique_raw,
            packet_digest=packet.packet_digest,
            require_packet_digest=True,
        )
    except ValueError as exc:
        raise Phase5CliError("critic packet failed blind-independence validation") from exc
    if not critique.is_independent:
        raise Phase5CliError("finalization requires an independent blind visual critique")
    status = structural.status
    if status is Phase5Status.PASS:
        status = critique.verdict
    assurance_status = Phase5Status.PASS_WITH_LIMITATIONS if status is Phase5Status.PASS else status
    prior_receipt = (
        cast(
            dict[str, object],
            dict(read_json_mapping(evidence_root / "builder-invocation-receipt.json")),
        )
        if version == "artifact_v2"
        else None
    )
    prior_attempts = prior_receipt.get("attempt_count", 0) if prior_receipt is not None else 0
    current_attempts = receipt.get("attempt_count", 0)
    total_builder_invocations = sum(
        value for value in (prior_attempts, current_attempts) if isinstance(value, int)
    )
    if version == "artifact_v2" and (
        not (evidence_root / "verification-v1.json").is_file()
        or not (evidence_root / "critique-v1.json").is_file()
    ):
        raise Phase5CliError("artifact_v2 finalization requires retained artifact_v1 evidence")
    if version == "artifact_v2" and prior_receipt is not None:
        prior_identity = _receipt_identity(evidence_root, task, "artifact_v1", prior_receipt)
        prior_artifact = artifact_from_receipt(
            task,
            prior_receipt,
            version="artifact_v1",
            expected_identity=prior_identity,
        )
        if artifact.parent_artifact_digest != prior_artifact.digest:
            raise Phase5CliError("artifact_v2 parent does not match artifact_v1")
        for prior_evidence_name in ("verification-v1.json", "critique-v1.json"):
            prior_evidence = read_json_mapping(evidence_root / prior_evidence_name)
            if prior_evidence.get("artifact_digest") != prior_artifact.digest:
                raise Phase5CliError(f"{prior_evidence_name} is not bound to artifact_v1")
    final_structural = replace(
        structural,
        verification_id=f"FINAL-VER-P5-V{suffix}",
        created_at=int(time.time()),
        digest="",
    )
    assurance = AssuranceReport(
        task.run_id,
        assurance_status,
        "A",
        "Native browser-boundary verification and a blind visual critique completed",
        (
            "EXTERNAL_VERIFIER_NOT_ELIGIBLE",
            "HOST_LOAD_UNOBSERVABLE",
            "REPAIR_APPLIED"
            if version == "artifact_v2"
            else (
                "NO_REPAIR_REQUIRED_FOR_THIS_PILOT"
                if not needs_repair(critique)
                else "REPAIR_REQUIRED_AND_PENDING"
            ),
        ),
        tuple(
            item.finding_id
            for item in final_structural.findings
            if item.severity in {FindingSeverity.CRITICAL, FindingSeverity.HIGH}
        ),
        artifact.digest,
        final_structural.digest,
        critique.packet_digest,
        int(time.time()),
    )
    composition = CompositionReceipt(
        task.task_id,
        task.run_id,
        status,
        FIXED_GRAPH,
        (
            "DESIGN_BUILDER",
            "STRUCTURAL_VERIFICATION",
            "VISUAL_CRITIQUE",
            *(("OPTIONAL_REPAIR",) if version == "artifact_v2" else ()),
            "FINAL_VERIFICATION",
            "ASSURANCE",
        ),
        total_builder_invocations,
        2 if version == "artifact_v2" else 1,
        2 if version == "artifact_v2" else 1,
        1 if version == "artifact_v2" else 0,
        ("artifact_v1", "artifact_v2") if version == "artifact_v2" else ("artifact_v1",),
        ("verification-v1", "critique-v1") if version == "artifact_v2" else (),
        "BLOCKED:EXTERNAL_VERIFIER_NOT_ELIGIBLE",
    )
    write_public_json(writer, f"verification-v{suffix}.json", structural)
    write_public_json(writer, f"blind-packet-v{suffix}.json", packet)
    write_public_json(writer, f"critique-v{suffix}.json", critique)
    write_public_json(writer, "final-verification.json", final_structural)
    write_public_json(writer, "assurance.json", assurance)
    write_public_json(writer, "composition-receipt.json", composition)
    writer.write_text(
        "final-summary.md",
        _summary_markdown(
            task,
            artifact,
            renders,
            final_structural,
            critique,
            assurance,
            composition,
        ),
    )
    return {
        "schema_version": "P5-FINAL-1",
        "status": assurance.status,
        "support_level": assurance.support_level,
        "artifact_digest": artifact.digest,
        "verification_digest": final_structural.digest,
        "critique_digest": critique.packet_digest,
        "render_paths": tuple(item.path for item in renders),
        "open_findings": sum(item.status == "OPEN" for item in critique.findings),
        "evidence_root": str(evidence_root),
    }


def prepare_review(root: Path, arguments: argparse.Namespace) -> dict[str, object]:
    task = load_task(_task_path(root, arguments.task), project_root=root)
    evidence_root = _evidence_path(root, arguments.evidence_dir)
    writer = EvidenceWriter(evidence_root)
    version = getattr(arguments, "artifact_version", "artifact_v1")
    suffix = version_suffix(version)
    receipt_name = (
        "builder-invocation-receipt.json"
        if version == "artifact_v1"
        else "builder-repair-receipt.json"
    )
    receipt = cast(
        dict[str, object],
        dict(read_json_mapping(evidence_root / receipt_name)),
    )
    artifact = artifact_from_receipt(task, receipt, version=version)
    renders = render_records(
        root,
        evidence_root,
        arguments.desktop,
        arguments.mobile,
        artifact_version=version,
    )
    packet = make_blind_packet(task, artifact, renders)
    write_public_json(writer, f"blind-packet-v{suffix}.json", packet)
    request = {
        "schema_version": "P5-BLIND-REQUEST-1",
        "benchmark_id": packet.benchmark_id,
        "run_id": packet.run_id,
        "artifact_version": artifact.version,
        "artifact_path": artifact.path,
        "artifact_digest": artifact.digest,
        "render_paths": tuple(item.path for item in renders),
        "render_viewports": tuple(item.viewport for item in renders),
        "acceptance_criteria": packet.acceptance_criteria,
        "packet_digest": packet.packet_digest,
        "builder_rationale_withheld": packet.builder_rationale_withheld,
        "self_score_withheld": packet.self_score_withheld,
        "instructions": (
            "Inspect the bound artifact and both native renders independently. "
            "Return a JSON critique only; do not modify the workspace."
        ),
    }
    write_public_json(writer, f"review-request-v{suffix}.json", request)
    return {
        "schema_version": "P5-REVIEW-1",
        "status": Phase5Status.PASS,
        "packet_digest": packet.packet_digest,
        "artifact_digest": artifact.digest,
        "render_paths": tuple(item.path for item in renders),
        "review_request": str(evidence_root / f"review-request-v{suffix}.json"),
    }
