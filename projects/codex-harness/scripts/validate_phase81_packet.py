"""Read-only integrity checks for the Phase 8.1 evidence handoff.

This module is the factual verifier for a frozen packet.  It never creates,
changes or removes evidence.  Packet materializers and the host remain
responsible for writing their own receipts; this verifier only reads the
structured handoff and reports deterministic observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ALLOWED_COMPOSITION_STATUSES = frozenset(
    {
        "PROVEN_WITH_HOST_LOAD_EVENT",
        "PROVEN_WITH_OBSERVABLE_ALTERNATIVE_CAUSALITY",
        "PARTIAL",
        "BLOCKED",
        "INVALID",
    }
)
ALLOWED_REPORT_STATUSES = frozenset(
    {"PASS", "PASS_WITH_LIMITATIONS", "PARTIAL", "BLOCKED", "FAIL", "INVALID"}
)
SOURCE_FILES = ("index.html", "styles.css", "app.js", "fixture_server.py")
CURRENT_PACKET_IDENTITIES = (
    "readiness",
    "closeout-index",
    "review-manifest",
    "review-attestation",
    "runtime-eval-report",
    "verifier-report",
)
REQUIRED_PACKET_FILES = (
    "readiness.json",
    "closeout-index.json",
    "review-manifest.json",
    "review-attestation.json",
    "verifier-report.json",
    "runtime-eval-report.json",
    "runtime-eval-classification.json",
    "runtime-eval-traceability.json",
    "structural-eval-report.json",
    "composition-proof.json",
    "composition-receipt.json",
    "composition-timeline.json",
    "browser-evidence.json",
    "frontend-package-validation.json",
    "coverage-summary.json",
    "finding-ledger.json",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _without(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {name: item for name, item in value.items() if name != key}


def validate_composition_status(status: Any) -> list[str]:
    """Return errors for a composition status outside the formal vocabulary."""

    if status in ALLOWED_COMPOSITION_STATUSES:
        return []
    return [
        f"composition status {status!r} is not one of "
        f"{sorted(ALLOWED_COMPOSITION_STATUSES)}"
    ]


def validate_identity(records: Mapping[str, Any], current_head: str) -> list[str]:
    """Ensure every current packet envelope is bound to the observed HEAD."""

    errors: list[str] = []
    for name in CURRENT_PACKET_IDENTITIES:
        record = records.get(name)
        if not isinstance(record, Mapping):
            errors.append(f"{name} is not a JSON object")
            continue
        if record.get("repository_head") != current_head:
            errors.append(
                f"{name}.repository_head={record.get('repository_head')!r} "
                f"does not match current HEAD {current_head!r}"
            )
    for name in ("readiness", "review-attestation"):
        record = records.get(name)
        if isinstance(record, Mapping) and record.get("reviewed_head") != current_head:
            errors.append(
                f"{name}.reviewed_head={record.get('reviewed_head')!r} "
                f"does not match current HEAD {current_head!r}"
            )
    return errors


def _safe_relative(path_value: Any) -> str | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != path_value:
        return None
    return path_value


def validate_review_manifest(manifest: Mapping[str, Any], evidence_root: Path) -> list[str]:
    """Rehash all manifest entries and the non-recursive manifest envelope."""

    errors: list[str] = []
    entries = manifest.get("entries")
    excluded = manifest.get("excluded_envelopes")
    if not isinstance(entries, list) or not isinstance(excluded, list):
        return ["manifest entries/excluded_envelopes have invalid shape"]
    excluded_paths = {item for item in excluded if isinstance(item, str)}
    seen: set[str] = set()
    for item in entries:
        if not isinstance(item, Mapping):
            errors.append("manifest contains a non-object entry")
            continue
        relative = _safe_relative(item.get("path"))
        if relative is None:
            errors.append(f"manifest path is unsafe: {item.get('path')!r}")
            continue
        if relative in seen:
            errors.append(f"manifest path is duplicated: {relative}")
        seen.add(relative)
        if relative in excluded_paths:
            errors.append(f"manifest includes an excluded envelope: {relative}")
        path = evidence_root / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"manifest entry is missing or unsafe: {relative}")
            continue
        if item.get("bytes") != path.stat().st_size:
            errors.append(f"manifest byte count mismatch: {relative}")
        if item.get("sha256") != _file_digest(path):
            errors.append(f"manifest digest mismatch: {relative}")
    declared_digest = manifest.get("manifest_digest")
    if declared_digest != _digest(_without(manifest, "manifest_digest")):
        errors.append("manifest_digest does not match the manifest body")
    return errors


def _load_json(evidence_root: Path, relative: str) -> Mapping[str, Any]:
    path = evidence_root / relative
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(relative)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{relative} is not a JSON object")
    return value


def _tree_digest(root: Path) -> str:
    payload = "\n".join(f"{name}:{_file_digest(root / name)}" for name in SOURCE_FILES)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_git_head(repository_root: Path) -> str:
    """Read a git HEAD without invoking a shell or mutating the repository."""

    git_path = repository_root / ".git"
    if git_path.is_file():
        git_dir_line = git_path.read_text(encoding="utf-8").strip()
        if not git_dir_line.startswith("gitdir:"):
            raise ValueError("unsupported gitdir file")
        git_path = (repository_root / git_dir_line.split(":", 1)[1].strip()).resolve()
    head_path = git_path / "HEAD"
    head = head_path.read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head
    reference = head[5:]
    ref_path = git_path / reference
    if ref_path.is_file():
        return ref_path.read_text(encoding="utf-8").strip()
    packed = git_path / "packed-refs"
    for line in packed.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and not line.startswith("^"):
            commit, ref = line.split(" ", 1)
            if ref == reference:
                return commit
    raise FileNotFoundError(f"git ref is unavailable: {reference}")


def _package_fingerprint(path: Path) -> str:
    try:
        from harness_kernel.phase7_backend import package_fingerprint
    except ModuleNotFoundError as exc:
        raise RuntimeError("harness_kernel is unavailable; set PYTHONPATH=src") from exc
    return package_fingerprint(path)


def _add_check(
    checks: list[dict[str, Any]], name: str, condition: bool, details: str
) -> None:
    checks.append({"name": name, "status": "PASS" if condition else "FAIL", "details": details})


def _load_packet(evidence_root: Path) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    packet: dict[str, Mapping[str, Any]] = {}
    errors: list[str] = []
    for relative in REQUIRED_PACKET_FILES:
        try:
            packet[relative.removesuffix(".json")] = _load_json(evidence_root, relative)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{relative}: {exc}")
    return packet, errors


def _path_from_project_ref(evidence_root: Path, value: Any) -> Path:
    if not isinstance(value, str):
        raise ValueError("path reference is not a string")
    prefix = "evidence/phase-8.1/"
    if value.startswith(prefix):
        value = value.removeprefix(prefix)
    relative = _safe_relative(value)
    if relative is None:
        raise ValueError(f"unsafe path reference: {value!r}")
    return evidence_root / relative


def _capture_metadata_errors(
    capture: Mapping[str, Any],
    path: Path,
    expected_run: Any,
    expected_artifact: Any,
) -> list[str]:
    """Check the metadata that makes a browser capture independently bindable."""

    errors: list[str] = []
    if capture.get("artifact_digest") != expected_artifact:
        errors.append(f"browser envelope artifact digest mismatch: {path.name}")
    if capture.get("composition_run") != expected_run:
        errors.append(f"browser envelope composition run mismatch: {path.name}")
    if capture.get("observer") != "Playwright MCP Chromium browser observer":
        errors.append(f"browser envelope observer is not explicit: {path.name}")
    if not isinstance(capture.get("captured_at_ns"), int):
        errors.append(f"browser envelope timestamp is missing: {path.name}")
    if path.suffix.lower() == ".json" and path.name not in {
        "server-process.json",
        "server-process-011.json",
    }:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"browser capture JSON is unreadable: {path.name}: {exc}")
        else:
            if not isinstance(value, Mapping):
                errors.append(f"browser capture JSON is not an object: {path.name}")
            else:
                for key in ("run_id", "source_digest", "artifact_digest", "observer"):
                    if value.get(key) != (
                        expected_run
                        if key == "run_id"
                        else "Playwright MCP Chromium browser observer"
                        if key == "observer"
                        else expected_artifact
                    ):
                        errors.append(f"browser capture metadata mismatch: {path.name}:{key}")
                if not isinstance(value.get("captured_at_ns"), int):
                    errors.append(f"browser capture timestamp is missing: {path.name}")
    return errors


def validate_packet(
    evidence_root: Path,
    repository_root: Path,
    *,
    current_head: str | None = None,
    handoff: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one exact packet and return a report without writing it."""

    evidence_root = evidence_root.resolve(strict=True)
    repository_root = repository_root.resolve(strict=True)
    observed_head = current_head or _read_git_head(repository_root)
    packet, load_errors = _load_packet(evidence_root)
    checks: list[dict[str, Any]] = []
    errors = list(load_errors)
    records = {
        name: packet.get(name)
        for name in CURRENT_PACKET_IDENTITIES
        if name in packet
    }
    identity_errors = validate_identity(records, observed_head)
    errors.extend(identity_errors)
    _add_check(checks, "current_head_identity", not identity_errors, observed_head)

    manifest = packet.get("review-manifest")
    if manifest is not None:
        manifest_errors = validate_review_manifest(manifest, evidence_root)
        errors.extend(manifest_errors)
        _add_check(checks, "review_manifest_integrity", not manifest_errors, "entry hashes match")

    proof = packet.get("composition-proof", {})
    receipt = packet.get("composition-receipt", {})
    timeline = packet.get("composition-timeline", {})
    browser = packet.get("browser-evidence", {})
    runtime_report = packet.get("runtime-eval-report", {})
    classification = packet.get("runtime-eval-classification", {})
    structural = packet.get("structural-eval-report", {})
    package = packet.get("frontend-package-validation", {})
    coverage = packet.get("coverage-summary", {})
    ledger = packet.get("finding-ledger", {})
    verifier = packet.get("verifier-report", {})
    readiness = packet.get("readiness", {})
    attestation = packet.get("review-attestation", {})

    status_errors = validate_composition_status(receipt.get("status"))
    status_errors.extend(validate_composition_status(proof.get("status")))
    errors.extend(status_errors)
    _add_check(checks, "composition_status_vocabulary", not status_errors, "formal status vocabulary")

    source_root = evidence_root / "fixture" / "frontend" / "app"
    try:
        build_root = _path_from_project_ref(evidence_root, receipt["source"]["root"])
        composed_root = _path_from_project_ref(
            evidence_root, receipt["composed_artifact"]["root"]
        )
        source_tree_digest = _tree_digest(source_root)
        build_tree_digest = _tree_digest(build_root)
        composed_tree_digest = _tree_digest(composed_root)
        artifact_digest = proof["artifact_digest"]
        artifact_errors = (
            source_tree_digest != artifact_digest
            or build_tree_digest != artifact_digest
            or composed_tree_digest != artifact_digest
            or receipt["source"]["tree_digest"] != artifact_digest
            or receipt["composed_artifact"]["tree_digest"] != artifact_digest
        )
        if artifact_errors:
            errors.append("source, build and composed artifact tree digests are not identical")
        _add_check(checks, "exact_artifact_binding", not artifact_errors, artifact_digest)
    except (KeyError, OSError, ValueError) as exc:
        errors.append(f"artifact binding: {exc}")
        _add_check(checks, "exact_artifact_binding", False, str(exc))
        artifact_digest = None

    try:
        frontend_package = _package_fingerprint(
            repository_root / "projects" / "codex-harness" / ".harness" / "capabilities" / "frontend-engineering-vnext"
        )
        verifier_package = _package_fingerprint(
            repository_root / "projects" / "codex-harness" / ".harness" / "capabilities" / "verification-loop-vnext"
        )
        fingerprint_errors = (
            package.get("package_fingerprint") != frontend_package
            or attestation.get("frontend_fingerprint") != frontend_package
            or proof.get("frontend_fingerprint") != frontend_package
            or verifier.get("verifier_fingerprint") != verifier_package
            or attestation.get("verifier_fingerprint") != verifier_package
            or proof.get("verifier_fingerprint") != verifier_package
        )
        if fingerprint_errors:
            errors.append("frontend or verifier package fingerprint is stale or inconsistent")
        _add_check(
            checks,
            "current_package_fingerprints",
            not fingerprint_errors,
            f"frontend={frontend_package}; verifier={verifier_package}",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        errors.append(f"package fingerprint: {exc}")
        _add_check(checks, "current_package_fingerprints", False, str(exc))

    critical_false_pass_count = structural.get("critical_false_pass_count")
    structural_errors = (
        structural.get("status") != "PASS"
        or structural.get("scenario_count") != 60
        or structural.get("failures") != []
        or critical_false_pass_count != 0
        or structural.get("critical_false_pass") != []
        or not isinstance(structural.get("false_pass_guard_ids"), list)
    )
    if structural_errors:
        errors.append("structural evaluation does not prove zero critical false passes")
    _add_check(checks, "structural_false_pass_guard", not structural_errors, "60 scenarios; 0 observed false passes")

    runtime_errors = (
        classification.get("catalog_scenario_count") != 60
        or classification.get("counts", {}).get("runtime_required") != 33
        or classification.get("counts", {}).get("runtime_executed") != 33
        or classification.get("counts", {}).get("promotion_relevant_unresolved") != 0
        or runtime_report.get("summary", {}).get("runtime_evals_passed") != 33
        or runtime_report.get("summary", {}).get("promotion_relevant_unresolved") != 0
    )
    if runtime_errors:
        errors.append("promotion-relevant runtime classification is incomplete")
    _add_check(checks, "runtime_eval_closure", not runtime_errors, "33/33 runtime-required evals")

    browser_capture_errors: list[str] = []
    captures = browser.get("captures")
    if not isinstance(captures, list):
        browser_capture_errors.append("browser captures are not a list")
    else:
        for capture in captures:
            if not isinstance(capture, Mapping):
                browser_capture_errors.append("browser capture is not an object")
                continue
            relative = _safe_relative(capture.get("path"))
            if relative is None or not relative.startswith("browser/"):
                browser_capture_errors.append(f"unsafe browser capture path: {capture.get('path')!r}")
                continue
            path = evidence_root / relative
            if not path.is_file() or path.is_symlink():
                browser_capture_errors.append(f"missing browser capture: {relative}")
            elif capture.get("sha256") != _file_digest(path):
                browser_capture_errors.append(f"stale browser capture digest: {relative}")
    try:
        binding = _load_json(evidence_root, "browser/server-binding.json")
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        binding = {}
        browser_capture_errors.append(f"browser/server-binding.json: {exc}")
    expected_run = proof.get("run_id")
    for capture in captures if isinstance(captures, list) else []:
        if not isinstance(capture, Mapping):
            continue
        relative = _safe_relative(capture.get("path"))
        if relative is None:
            continue
        path = evidence_root / relative
        if path.is_file() and not path.is_symlink():
            browser_capture_errors.extend(
                _capture_metadata_errors(capture, path, expected_run, artifact_digest)
            )
    browser_errors = (
        browser.get("artifact_digest") != artifact_digest
        or browser.get("composition_run") != proof.get("run_id")
        or browser.get("browser", {}).get("engine") != "Chromium"
        or binding.get("artifactDigest") != artifact_digest
        or binding.get("status") != 200
        or binding.get("url") != binding.get("requestedUrl")
        or not str(binding.get("url", "")).startswith("http://127.0.0.1:")
        or bool(browser_capture_errors)
    )
    if browser_errors:
        errors.extend(browser_capture_errors)
        errors.append("browser evidence is not bound to the exact composed artifact")
    _add_check(checks, "browser_evidence_binding", not browser_errors, "capture hashes and HTTP binding")

    proof_errors = (
        proof.get("status") != "PROVEN_WITH_OBSERVABLE_ALTERNATIVE_CAUSALITY"
        or proof.get("source_digest") != artifact_digest
        or proof.get("artifact_digest") != artifact_digest
        or proof.get("browser_evidence_digest") != _file_digest(evidence_root / "browser-evidence.json")
        or proof.get("verification_digest") != verifier.get("verification_digest")
        or proof.get("Harness_observations", {}).get("global_mutations") != 0
        or proof.get("Harness_observations", {}).get("capability_file_mutations") != 0
        or proof.get("Harness_observations", {}).get("external_producer") is not False
        or proof.get("Harness_observations", {}).get("manual_mutation_during_run") is not False
        or proof.get("host_observations", {}).get("skill_load") != "HOST_LOAD_UNOBSERVABLE"
        or proof.get("proof_digest") != _digest(_without(proof, "proof_digest"))
    )
    if proof_errors:
        errors.append("composition proof is incomplete, stale or self-inconsistent")
    _add_check(checks, "composition_proof", not proof_errors, "observable alternative chain")

    timeline_events = timeline.get("events")
    timeline_errors: list[str] = []
    required_event_fields = {
        "sequence",
        "observed_at_ns",
        "event",
        "source",
        "run_id",
        "invocation_id",
        "capability",
        "source_digest",
        "artifact_digest",
        "observation_type",
    }
    if not isinstance(timeline_events, list) or not timeline_events:
        timeline_errors.append("timeline events are absent")
    else:
        timestamps: list[int] = []
        for event in timeline_events:
            if not isinstance(event, Mapping) or not required_event_fields <= set(event):
                timeline_errors.append("timeline event is missing identity fields")
                continue
            timestamps.append(event["observed_at_ns"])
            if (
                event["run_id"] != proof.get("run_id")
                or event["source_digest"] != artifact_digest
                or event["artifact_digest"] != artifact_digest
                or not isinstance(event["observed_at_ns"], int)
                or not event["invocation_id"]
                or not event["capability"]
            ):
                timeline_errors.append("timeline event identity does not match composition proof")
        if any(left >= right for left, right in zip(timestamps, timestamps[1:], strict=False)):
            timeline_errors.append("timeline timestamps are not strictly monotonic")
    if timeline.get("timeline_digest") != _digest(_without(timeline, "timeline_digest")):
        timeline_errors.append("timeline_digest does not match the timeline body")
    errors.extend(timeline_errors)
    _add_check(checks, "composition_timeline", not timeline_errors, "identity-rich monotonic event chain")

    finding_counts = ledger.get("counts", {})
    findings_errors = (
        finding_counts.get("open_actionable_high") != 0
        or finding_counts.get("promotion_blocking_high") != 0
        or finding_counts.get("open_actionable_medium") != 0
        or finding_counts.get("promotion_blocking_medium") != 0
    )
    if findings_errors:
        errors.append("actionable High or Medium findings remain open")
    _add_check(checks, "finding_ledger", not findings_errors, "zero actionable/promotion-blocking High and Medium")

    coverage_errors = (
        coverage.get("totals", {}).get("percent_covered", 0) < 80
        or coverage.get("totals", {}).get("percent_branches_covered", 0) < 80
    )
    if coverage_errors:
        errors.append("coverage is below the 80% line/branch threshold")
    _add_check(checks, "coverage", not coverage_errors, "line and branch coverage >= 80%")

    report_status = verifier.get("status")
    verifier_errors = (
        report_status not in ALLOWED_REPORT_STATUSES
        or verifier.get("repository_head") != observed_head
        or verifier.get("summary", {}).get("checks_failed") != 0
        or verifier.get("summary", {}).get("promotion_relevant_unresolved") != 0
        or verifier.get("verification_digest") != _digest(_without(verifier, "verification_digest"))
    )
    if verifier_errors:
        errors.append("verifier report is stale, failed or has an invalid self-digest")
    _add_check(checks, "verifier_report", not verifier_errors, "current bounded verifier report")

    attestation_errors = (
        attestation.get("repository_head") != observed_head
        or attestation.get("reviewed_head") != observed_head
        or attestation.get("manifest_digest") != manifest.get("manifest_digest")
        or attestation.get("composition_proof_status") != proof.get("status")
        or attestation.get("host_load_observability") != "HOST_LOAD_UNOBSERVABLE"
        or attestation.get("verdict") != "PASS_WITH_LIMITATIONS"
    )
    if attestation_errors:
        errors.append("review attestation is incomplete or stale")
    _add_check(checks, "review_attestation", not attestation_errors, "reviewed HEAD and promotion fields")

    exact_review_path = evidence_root / "independent-exact-packet-review.md"
    exact_review_ok = exact_review_path.is_file() and "PASS_WITH_LIMITATIONS" in exact_review_path.read_text(
        encoding="utf-8"
    )
    if not exact_review_ok:
        errors.append("independent exact-packet review is missing or not PASS_WITH_LIMITATIONS")
    _add_check(checks, "exact_packet_review", exact_review_ok, "fresh independent packet review")

    if handoff is not None:
        for field, actual in (
            ("repository_head", observed_head),
            ("artifact_digest", artifact_digest),
            ("composition_run", proof.get("run_id")),
        ):
            if field in handoff and handoff[field] != actual:
                errors.append(f"structured handoff mismatch for {field}")

    report: dict[str, Any] = {
        "schema_version": "P8.1-READONLY-VERIFIER-1",
        "task_id": "PHASE8.1-001",
        "status": "PASS_WITH_LIMITATIONS" if not errors else "FAIL",
        "repository_head": observed_head,
        "reviewed_head": observed_head,
        "frontend_fingerprint": attestation.get("frontend_fingerprint"),
        "verifier_fingerprint": verifier.get("verifier_fingerprint"),
        "composition_run": proof.get("run_id"),
        "artifact_digest": artifact_digest,
        "checks": checks,
        "summary": {
            "checks_total": len(checks),
            "checks_passed": sum(item["status"] == "PASS" for item in checks),
            "checks_failed": sum(item["status"] == "FAIL" for item in checks),
            "errors": len(errors),
        },
        "errors": errors,
        "limitations": [
            "HOST_LOAD_UNOBSERVABLE",
            "Chromium-only bounded browser evidence",
            "Synthetic loopback fixture; no production, release or security approval claim",
        ],
    }
    report["verification_digest"] = _digest(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=Path(__file__).parents[1] / "evidence" / "phase-8.1")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).parents[3])
    parser.add_argument("--handoff", type=Path)
    arguments = parser.parse_args()
    handoff: Mapping[str, Any] | None = None
    if arguments.handoff is not None:
        value = json.loads(arguments.handoff.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("handoff must be a JSON object")
        handoff = value
    report = validate_packet(
        arguments.evidence_root,
        arguments.repository_root,
        handoff=handoff,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
