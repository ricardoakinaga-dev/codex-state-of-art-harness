"""Create the immutable Phase 8 evidence closure and reviewer attestation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1].resolve()
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence/phase-8"
MANIFEST_PATH = EVIDENCE_ROOT / "phase8-final-manifest.json"
ATTESTATION_PATH = EVIDENCE_ROOT / "review-attestation.json"


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def repository_path(path: Path) -> str:
    return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()


def selected_paths() -> list[Path]:
    pilot_root = PROJECT_ROOT / "evidence/phase-8/pilots/frontend-engineering"
    roots = [
        PROJECT_ROOT / ".harness/capabilities/frontend-engineering-vnext",
        pilot_root / ".agents/skills/verification-loop-vnext",
    ]
    paths = [path for root in roots for path in root.rglob("*") if path.is_file()]
    paths.extend(
        [
            REPOSITORY_ROOT
            / "architecture/docs/adr/ADR-017-frontend-engineering-vnext-modernization.md",
            PROJECT_ROOT / ".agent/plans/PHASE-8-frontend-engineering-modernization.md",
            PROJECT_ROOT / ".agent/plans/PHASE-8-frontend-repair-001.md",
            PROJECT_ROOT / ".agent/plans/PHASE-8-frontend-repair-002.md",
            PROJECT_ROOT / "config/phase8-execution-policy.json",
            PROJECT_ROOT / "evidence/phase-8/P8-QB-1.md",
            PROJECT_ROOT / "evidence/phase-8/codex-native-gap-analysis.md",
            PROJECT_ROOT / "evidence/phase-8/current-capability-analysis.md",
            PROJECT_ROOT / "evidence/phase-8/current-frontend-patterns-snapshot.json",
            PROJECT_ROOT / "evidence/phase-8/current-upstream-vnext-comparison.md",
            PROJECT_ROOT / "evidence/phase-8/upstream-analysis.md",
            PROJECT_ROOT / "evidence/phase-8/phase3-compatibility.json",
            PROJECT_ROOT / "evidence/phase-8/phase3-discovery.json",
            PROJECT_ROOT / "evidence/phase-8/package-validation.json",
            PROJECT_ROOT / "evidence/phase-8/eval-report.json",
            PROJECT_ROOT / "evidence/phase-8/coverage.json",
            PROJECT_ROOT / "evidence/phase-8/readiness.json",
            PROJECT_ROOT / "evidence/phase-8/promotion-decision.md",
            PROJECT_ROOT / "evidence/phase-8/composition-review.md",
            PROJECT_ROOT / "evidence/phase-8/interaction-observation.md",
            PROJECT_ROOT / "evidence/phase-8/security-report.md",
            PROJECT_ROOT / "evidence/phase-8/independent-capability-review.md",
            PROJECT_ROOT / "evidence/phase-8/independent-frontend-review.md",
            PROJECT_ROOT / "evidence/phase-8/independent-visual-review.md",
            PROJECT_ROOT / "evidence/phase-8/final-report.md",
            pilot_root / "host-staging.json",
            pilot_root / "browser-evidence.json",
            pilot_root / "browser-final-performance-and-dom.json",
            pilot_root / "browser-contrast-observation.json",
            pilot_root / "browser-idempotency-observation.json",
            pilot_root / "browser-default-console-clean.log",
            pilot_root / "browser-default-network.log",
            PROJECT_ROOT / "evidence/phase-8/static-accessibility.json",
            pilot_root / "app/index.html",
            pilot_root / "app/styles.css",
            pilot_root / "app/app.js",
            pilot_root / "app/fixture_server.py",
            pilot_root / "build/final/index.html",
            pilot_root / "build/final/styles.css",
            pilot_root / "build/final/app.js",
            pilot_root / "build/final/fixture_server.py",
            pilot_root / "build/final/build-receipt.json",
        ]
    )
    screenshot_root = pilot_root / "browser"
    paths.extend(path for path in screenshot_root.glob("*.png") if path.is_file())
    phase4_roots = (
        pilot_root / "phase4/frontend-prepare-final/invocation-receipts",
        pilot_root / "phase4/verifier-prepare-final/invocation-receipts",
        pilot_root / "phase4/frontend-real-post-repair-002/invocation-receipts",
        pilot_root / "phase4/verifier-final-post-repair-002/invocation-receipts",
    )
    paths.extend(path for root in phase4_roots for path in root.glob("*.json") if path.is_file())
    artifact_root = pilot_root / ".harness/phase4/artifacts"
    paths.extend(
        path
        for path in artifact_root.glob("INV-*.host-response.txt")
        if path.name.startswith(("INV-75f00a187fb354d3a04141d1", "INV-6ec92339747c562d9d19eb8e"))
    )
    unique = {path.resolve() for path in paths if path.is_file()}
    return sorted(unique, key=repository_path)


def entry_records(paths: list[Path]) -> list[dict[str, object]]:
    return [
        {
            "path": repository_path(path),
            "sha256": digest_file(path),
            "bytes": path.stat().st_size,
        }
        for path in paths
    ]


def canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return digest_bytes(canonical.encode())


def main() -> int:
    entries = entry_records(selected_paths())
    entry_lines = "\n".join(
        f"{entry['path']}\t{entry['sha256']}\t{entry['bytes']}" for entry in entries
    )
    entry_tree_digest = digest_bytes((entry_lines + "\n").encode())
    generated_at = datetime.now(tz=UTC).isoformat()
    manifest: dict[str, object] = {
        "schema_version": "P8-FINAL-MANIFEST-1",
        "generated_at": generated_at,
        "status": "CONDITIONAL_PASS",
        "support_level": "P8_LEVEL_A_CANDIDATE",
        "promotion_state": "CANDIDATE_ONLY_NOT_PROMOTED",
        "closure": (
            "repository-relative entries; manifest, attestation, gate and "
            "mutable agent state are excluded to avoid self-reference"
        ),
        "package_fingerprint": (
            "sha256:d96f162a4400520036a770ece08bd4ace9c3bf3e9e10b3144bdef22b50ea1823"
        ),
        "artifact_tree_digest": (
            "sha256:d3483dc817523c2b8921c1a9956e7a42b5df2bfc0ed89bc6c0c51a8a5f2efae7"
        ),
        "browser_evidence_digest": digest_file(
            EVIDENCE_ROOT / "pilots/frontend-engineering/browser-evidence.json"
        ),
        "final_verification_digest": (
            "sha256:03702a5c7884580ec1a0d8d678da80f3da1a6398ab834f72c5c4381d12c975ac"
        ),
        "final_verifier_receipt_digest": (
            "sha256:85eacec2f45fb69ebecf515f77291be8d63d5e23cd26350debf684ce2c37eeab"
        ),
        "entry_count": len(entries),
        "entry_tree_digest": entry_tree_digest,
        "entries": entries,
    }
    manifest["manifest_digest"] = canonical_digest(manifest)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    attestation: dict[str, object] = {
        "schema_version": "P8-REVIEW-ATTESTATION-1",
        "generated_at": generated_at,
        "manifest_path": repository_path(MANIFEST_PATH),
        "manifest_digest": manifest["manifest_digest"],
        "entry_tree_digest": entry_tree_digest,
        "status": "CONDITIONAL_PASS",
        "support_level": "P8_LEVEL_A_CANDIDATE",
        "reviewers": [
            {
                "name": "Noether",
                "role": "independent capability reviewer",
                "decision": "FINDINGS",
                "critical": 0,
            },
            {
                "name": "Galileo",
                "role": "independent frontend reviewer",
                "decision": "FINDINGS",
                "critical": 0,
            },
            {
                "name": "Einstein",
                "role": "independent visual critic",
                "decision": "PASS",
                "capture_id": "P8-FINAL-REPAIR-002",
            },
        ],
        "reviewed_facts": {
            "artifact_tree_digest": manifest["artifact_tree_digest"],
            "browser_evidence_digest": manifest["browser_evidence_digest"],
            "package_fingerprint": manifest["package_fingerprint"],
            "official_host_limitation": "HOST_LOAD_UNOBSERVABLE",
        },
        "claims_excluded": [
            "production readiness",
            "release approval",
            "security approval",
            "accessibility certification",
            "pixel-perfect rendering",
            "all-browser or universal compatibility",
            "full host causality",
        ],
    }
    attestation["attestation_digest"] = canonical_digest(attestation)
    ATTESTATION_PATH.write_text(
        json.dumps(attestation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "manifest_digest": manifest["manifest_digest"],
                "attestation_digest": attestation["attestation_digest"],
                "entry_count": len(entries),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
