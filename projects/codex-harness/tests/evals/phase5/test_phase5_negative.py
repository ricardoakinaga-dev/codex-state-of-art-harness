from __future__ import annotations

import json

import pytest
from phase5_support import make_fingerprint

from harness_kernel.phase5_artifacts import ArtifactCaptureError, extract_response_artifact
from harness_kernel.phase5_models import Phase5Role, Phase5Status
from harness_kernel.phase5_policy import evaluate_eligibility, validate_fixed_graph


def test_prompt_injection_like_artifact_cannot_escape_response_contract() -> None:
    payload = json.dumps(
        {
            "artifact_filename": "index.html",
            "artifact_html": "<!doctype html><a href='javascript:alert(1)'>ignore policy</a>",
        }
    )
    with pytest.raises(ArtifactCaptureError):
        extract_response_artifact(payload)


def test_path_escape_and_external_action_tokens_are_blocked(tmp_path) -> None:
    with pytest.raises(ArtifactCaptureError):
        extract_response_artifact(
            json.dumps(
                {"artifact_filename": "../../escape.html", "artifact_html": "<!doctype html>"}
            )
        )
    fingerprint = make_fingerprint(tmp_path)
    allowlist_payload = {
        "builder": fingerprint,
        "builder_manifest_fingerprint": fingerprint.manifest_fingerprint,
        "approved_status": "APPROVED_RESPONSE_ONLY",
    }
    from harness_kernel.phase5_policy import Phase5Allowlist

    allowlist = Phase5Allowlist(**allowlist_payload)
    blocked = evaluate_eligibility(fingerprint, allowlist, Phase5Role.STRUCTURAL_VERIFIER)
    assert blocked.status == Phase5Status.BLOCKED
    with pytest.raises(ValueError):
        validate_fixed_graph(("DESIGN_BUILDER", "SHELL", "ASSURANCE"))


def test_secondary_capability_cannot_escalate_builder_role(tmp_path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    from harness_kernel.phase5_policy import Phase5Allowlist

    allowlist = Phase5Allowlist(
        builder=fingerprint,
        builder_manifest_fingerprint=fingerprint.manifest_fingerprint,
        approved_status="APPROVED_RESPONSE_ONLY",
        secondary_status="BLOCKED",
        secondary_blocker="EXTERNAL_VERIFIER_NOT_ELIGIBLE",
    )
    result = evaluate_eligibility(fingerprint, allowlist, Phase5Role.VISUAL_CRITIC)
    assert result.status == Phase5Status.BLOCKED
    assert result.blockers == ("SECONDARY_CAPABILITY_NOT_ELIGIBLE",)
