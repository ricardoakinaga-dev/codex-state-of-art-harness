"""Close one exact Phase 4 packet after an independent read-only review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import cast

from publish_phase4_evidence import _payload_paths, _repository_bound_files

from harness_kernel.phase4_evidence import EvidenceWriter, build_review_manifest, redact_paths

PROJECT_ROOT = Path(__file__).parents[1].resolve()
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-4"
ALLOWED_VERDICTS = ("PASS_WITH_LIMITATIONS", "CONDITIONAL_PASS", "FAIL")
_REVIEWER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REVIEW_SUMMARY_PATTERNS = {
    "verdict": re.compile(
        r"^Review verdict:\s*(PASS_WITH_LIMITATIONS|CONDITIONAL_PASS|FAIL)\s*$",
        re.MULTILINE,
    ),
    "critical": re.compile(r"^Critical findings:\s*(\d+)\s*$", re.MULTILINE),
    "high": re.compile(r"^High findings:\s*(\d+)\s*$", re.MULTILINE),
    "medium": re.compile(r"^Medium findings:\s*(\d+)\s*$", re.MULTILINE),
    "low": re.compile(r"^Low findings:\s*(\d+)\s*$", re.MULTILINE),
}


def _read_json(relative: str) -> dict[str, object]:
    path = EVIDENCE_ROOT / relative
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"required evidence is unreadable: {relative}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"required evidence is not an object: {relative}")
    return payload


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT.parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _review_text(path: Path) -> str:
    try:
        metadata = path.lstat()
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            raise RuntimeError("review text file must be a regular file")
        if metadata.st_size > 256 * 1024:
            raise RuntimeError("review text file exceeds its bound")
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError("review text file could not be read") from exc
    if not text.strip():
        raise RuntimeError("review text file is empty")
    sanitized = redact_paths(text)
    if not isinstance(sanitized, str):
        raise RuntimeError("review text sanitization failed")
    return sanitized


def _file_entries(manifest: dict[str, object]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for path in sorted(EVIDENCE_ROOT.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"evidence packet contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = str(path.relative_to(EVIDENCE_ROOT))
        if relative == "review-closure.json":
            continue
        data = path.read_bytes()
        entries.append(
            {
                "scope": "evidence",
                "path": relative,
                "size_bytes": len(data),
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
        )
    if not entries:
        raise RuntimeError("the Phase 4 evidence packet is empty")
    raw_manifest_entries = manifest.get("entries")
    if not isinstance(raw_manifest_entries, list):
        raise RuntimeError("the primary manifest has no entries")
    repository_entries = [
        dict(item)
        for item in raw_manifest_entries
        if isinstance(item, dict) and item.get("scope") == "repository"
    ]
    if not repository_entries:
        raise RuntimeError("the primary manifest has no repository-bound entries")
    entries.extend(repository_entries)
    return entries


def _parse_review_summary(text: str) -> dict[str, object]:
    """Require machine-readable reviewer counts before writing a closeout."""

    parsed: dict[str, object] = {}
    for name, pattern in _REVIEW_SUMMARY_PATTERNS.items():
        matches = pattern.findall(text)
        if len(matches) != 1:
            raise RuntimeError(f"independent review must contain exactly one {name} summary")
        value = matches[0]
        parsed[name] = value if name == "verdict" else int(value)
    return parsed


def _closure(entries: list[dict[str, object]]) -> str:
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewer-verdict", choices=ALLOWED_VERDICTS, required=True)
    parser.add_argument("--review-text-file", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not EVIDENCE_ROOT.is_dir():
        raise RuntimeError("Phase 4 evidence root is missing")
    if (EVIDENCE_ROOT / "review-closure.json").exists():
        raise RuntimeError("Phase 4 evidence is already closed")
    final_run = _read_json("final-run.json")
    host_result = _read_json("host-result.json").get("result")
    manifest = _read_json("review-manifest.json")
    current_readiness = _read_json("readiness.json")
    if final_run.get("status") != "SUCCESS":
        raise RuntimeError("only a successful controlled pilot can be closed")
    if not isinstance(host_result, dict) or host_result.get("mcp_event_count") != 0:
        raise RuntimeError("the final packet does not prove zero MCP protocol events")
    manifest_closure = manifest.get("payload_closure")
    if not isinstance(manifest_closure, str) or not manifest_closure.startswith("sha256:"):
        raise RuntimeError("the primary review manifest has no closure")
    recomputed_manifest = build_review_manifest(
        EVIDENCE_ROOT,
        _payload_paths(),
        bound_files=_repository_bound_files(),
    )
    if recomputed_manifest != manifest:
        raise RuntimeError("the primary review manifest is stale or incomplete")
    if current_readiness.get("review_manifest") != manifest_closure:
        raise RuntimeError("readiness does not reference the current primary manifest")
    pending_attestation = _read_json("review-attestation.json")
    if pending_attestation.get("manifest_closure") != manifest_closure:
        raise RuntimeError("review attestation does not reference the current primary manifest")
    if _REVIEWER_ID_PATTERN.fullmatch(args.reviewer_id) is None:
        raise RuntimeError("reviewer ID is invalid")
    for field in ("tests", "coverage", "ruff", "mypy", "security"):
        value = current_readiness.get(field)
        if not isinstance(value, str) or not value.strip() or "PENDING" in value.upper():
            raise RuntimeError(f"readiness metric is incomplete: {field}")
    reviewed_head = _git_head()
    packet_head = current_readiness.get("reviewed_head")
    if packet_head != reviewed_head:
        raise RuntimeError("repository HEAD changed after the packet was captured")
    reviewer_text = _review_text(args.review_text_file)
    status = args.reviewer_verdict
    summary = _parse_review_summary(reviewer_text)
    if summary["verdict"] != status:
        raise RuntimeError("reviewer verdict does not match the declared closeout verdict")
    critical = cast(int, summary["critical"])
    high = cast(int, summary["high"])
    medium = cast(int, summary["medium"])
    low = cast(int, summary["low"])
    if status == "FAIL":
        raise RuntimeError("FAIL review verdict cannot close a Phase 4 packet")
    if critical or high:
        raise RuntimeError("Critical or High findings must be fixed before closeout")
    writer = EvidenceWriter(EVIDENCE_ROOT)
    writer.write_text(
        "independent-review.md",
        "# Independent read-only review\n\n"
        f"Reviewer: `{args.reviewer_id}`\n"
        f"Verdict: `{args.reviewer_verdict}`\n\n"
        "The reviewer inspected the exact Phase 4 packet, its primary manifest, "
        "repository-bound files and final host evidence. The verbatim sanitized "
        "review record follows.\n\n" + reviewer_text + "\n",
    )
    writer.write_json(
        "review-attestation.json",
        {
            "schema_version": "P4-REVIEW-ATTESTATION-1",
            "review_status": status,
            "reviewer_id": args.reviewer_id,
            "reviewer_verdict": args.reviewer_verdict,
            "critical": critical,
            "high": high,
            "medium": medium,
            "low": low,
            "manifest_closure": manifest_closure,
            "reviewed_head": reviewed_head,
            "scope": (
                "exact Phase 4 packet; independent read-only review; "
                "no source or global state mutation"
            ),
        },
    )
    readiness = {
        "phase": "PHASE4-001",
        "status": status,
        "quality_bar": "P4-QB-1",
        "reviewed_head": reviewed_head,
        "phase2_base": "FROZEN",
        "phase3_base": "FROZEN",
        "host_support_level": "P4_LEVEL_B",
        "pilot_capabilities": current_readiness.get("pilot_capabilities", []),
        "pilot_fingerprints": current_readiness.get("pilot_fingerprints", []),
        "execution_mode": current_readiness.get("execution_mode", "CONTROLLED_REAL"),
        "real_invocation_count": current_readiness.get("real_invocation_count", 1),
        "evidenced_real_invocation_count": current_readiness.get(
            "evidenced_real_invocation_count",
            current_readiness.get("real_invocation_count", 1),
        ),
        "attempt_count": current_readiness.get("attempt_count", 1),
        "unresolved_reservation_count": current_readiness.get("unresolved_reservation_count", 0),
        "successful_final_invocation_count": current_readiness.get(
            "successful_final_invocation_count", 1
        ),
        "load_observation_status": host_result.get("load_observation", "HOST_LOAD_UNOBSERVABLE"),
        "tests": current_readiness.get("tests", "recorded in test-report.md"),
        "coverage": current_readiness.get("coverage", "recorded in coverage-report.md"),
        "ruff": current_readiness.get("ruff", "PASS"),
        "mypy": current_readiness.get("mypy", "PASS"),
        "benchmark": "P4-BENCH-1",
        "security": current_readiness.get("security", "PASS_WITH_LIMITATIONS"),
        "phase2_regression": current_readiness.get("phase2_regression", "PASS"),
        "phase3_regression": current_readiness.get("phase3_regression", "PASS"),
        "critical": critical,
        "high": high,
        "medium": medium,
        "low": low,
        "independent_review": status,
        "review_manifest": manifest_closure,
        "review_attestation": "review-attestation.json",
        "review_closure": "review-closure.json",
        "limitations": current_readiness.get(
            "limitations",
            [
                "HOST_LOAD_UNOBSERVABLE",
                "GLOBAL_METADATA_ONLY_AND_VOLATILE_SESSION_STATE_EXCLUDED",
                "BOUNDED_SCRIPT_FREE_PROJECT_LOCAL_PILOT_ONLY",
            ],
        ),
        "excluded_claims": [
            "PRODUCTION_READY",
            "AAA_VERIFIED",
            "ARBITRARY_SKILL_EXECUTION",
            "SAFE_ARBITRARY_CODE_EXECUTION",
            "MCP_COMPLETE",
            "PROVIDER_COMPLETE",
            "SUBAGENT_COMPLETE",
            "FULL_HOST_CAUSALITY",
            "GLOBAL_MUTATION_SAFE",
            "DISTRIBUTED_EXECUTION",
        ],
    }
    writer.write_json("readiness.json", readiness)
    writer.write_text(
        "final-report.md",
        "# Phase 4 final report\n\n"
        "## Result\n\n"
        f"`{status}` for the bounded `PHASE4-001` scope.\n\n"
        "## Scope\n\n"
        "One exact, project-local, script-free controlled-real pilot through the "
        "official Codex app-server boundary. Phase 2 and Phase 3 remain frozen.\n\n"
        "## Gates\n\n"
        "The P4-QB-1 blocking gates are closed within the declared bounded scope. "
        "The independent review findings are recorded as "
        f"Critical/High/Medium/Low = {critical}/{high}/{medium}/{low}; "
        "the exact-packet review is tied to the recomputed primary manifest.\n\n"
        "## Limitations\n\n"
        "The host turn and execution were observed, but Skill-load causality remains "
        "unobservable. Global checks are metadata-only for the declared stable roots; "
        "volatile parent-session history is excluded. The pilot does not authorize "
        "arbitrary Skills, tools, providers, MCP, shell, network, subagents or "
        "production operation.\n\n"
        "## Evidence\n\n"
        f"Primary manifest: `review-manifest.json` (`{manifest_closure}`). The full "
        "post-review packet is covered by `review-closure.json`; the attestation is "
        "`review-attestation.json`.\n\n"
        "## Deferred work\n\n"
        "Any broader Skill, tool/provider, MCP, Director, distributed or production "
        "boundary requires a new phase, policy, evidence packet and independent review.\n",
    )
    writer.write_text(
        "PHASE4-FROZEN.md",
        "# PHASE4-FROZEN\n\n"
        f"- Status: `{status}`\n"
        f"- Reviewed HEAD: `{reviewed_head}`\n"
        f"- Pilot capability: `{current_readiness.get('pilot_capabilities', [])}`\n"
        f"- Pilot fingerprint: `{current_readiness.get('pilot_fingerprints', [])}`\n"
        "- Host support: `P4_LEVEL_B`\n"
        f"- Review manifest: `review-manifest.json` (`{manifest_closure}`)\n"
        "- Independent attestation: `review-attestation.json`\n"
        "- Full packet closure: `review-closure.json`\n"
        f"- Tests: `{readiness['tests']}`\n"
        f"- Coverage: `{readiness['coverage']}`\n"
        f"- Critical/High/Medium/Low findings: `{critical} / {high} / {medium} / {low}`\n\n"
        "This freeze is limited to the exact bounded Phase 4 packet. Future changes "
        "require a new capture, manifest, independent review and freeze. Deferred "
        "work includes arbitrary execution, broader host capabilities and production "
        "readiness.\n",
    )
    entries = _file_entries(manifest)
    writer.write_json(
        "review-closure.json",
        {
            "schema_version": "P4-REVIEW-CLOSURE-1",
            "scope": "all final Phase 4 evidence files except this self-excluding closure",
            "entries": entries,
            "entry_count": len(entries),
            "closure": _closure(entries),
        },
    )
    print(json.dumps({"status": status, "reviewed_head": reviewed_head}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
