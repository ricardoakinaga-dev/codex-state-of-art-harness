from __future__ import annotations

import json

import pytest
from phase5_support import HOST_DIGEST, make_fingerprint, make_task

from harness_kernel.phase5_models import Phase5Role, Phase5Status
from harness_kernel.phase5_policy import (
    Phase5Allowlist,
    build_builder_request,
    evaluate_eligibility,
    validate_fixed_graph,
)


def test_exact_allowlist_accepts_only_the_pinned_package(tmp_path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    allowlist = Phase5Allowlist(
        builder=fingerprint,
        builder_manifest_fingerprint=fingerprint.manifest_fingerprint,
        approved_status="APPROVED_RESPONSE_ONLY",
    )
    report = evaluate_eligibility(fingerprint, allowlist, Phase5Role.DESIGN_BUILDER)
    assert report.status == Phase5Status.PASS
    assert report.route == "RESPONSE_ONLY_BUILDER"
    changed = make_fingerprint(tmp_path, package_digest="sha256:" + "9" * 64)
    blocked = evaluate_eligibility(changed, allowlist, Phase5Role.DESIGN_BUILDER)
    assert blocked.status == Phase5Status.BLOCKED
    assert "PACKAGE_FINGERPRINT_MISMATCH" in blocked.blockers


def test_scripts_and_bad_trust_never_become_builder_permission(tmp_path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    allowlist = Phase5Allowlist(
        builder=fingerprint,
        builder_manifest_fingerprint=fingerprint.manifest_fingerprint,
        approved_status="APPROVED_RESPONSE_ONLY",
    )
    scripted = make_fingerprint(tmp_path)
    object.__setattr__(scripted, "scripts", ("scripts/run.py",))
    blocked = evaluate_eligibility(scripted, allowlist, Phase5Role.DESIGN_BUILDER)
    assert blocked.status == Phase5Status.BLOCKED
    assert "PACKAGE_SCRIPTS_PRESENT" in blocked.blockers
    untrusted = make_fingerprint(tmp_path)
    object.__setattr__(untrusted, "trust", "REJECTED")
    blocked = evaluate_eligibility(untrusted, allowlist, Phase5Role.DESIGN_BUILDER)
    assert "TRUST_REJECTED" in blocked.blockers


def test_verification_loop_fallback_is_named_and_blocked(tmp_path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    allowlist = Phase5Allowlist(
        builder=fingerprint,
        builder_manifest_fingerprint=fingerprint.manifest_fingerprint,
        approved_status="APPROVED_RESPONSE_ONLY",
        secondary_status="BLOCKED",
        secondary_blocker="EXTERNAL_VERIFIER_NOT_ELIGIBLE",
    )
    report = evaluate_eligibility(fingerprint, allowlist, Phase5Role.STRUCTURAL_VERIFIER)
    assert report.status == Phase5Status.BLOCKED
    assert report.blockers == ("SECONDARY_CAPABILITY_NOT_ELIGIBLE",)
    assert allowlist.secondary_blocker == "EXTERNAL_VERIFIER_NOT_ELIGIBLE"


def test_fixed_graph_rejects_cycles_unknown_nodes_and_reordering() -> None:
    validate_fixed_graph(
        (
            "DESIGN_BUILDER",
            "STRUCTURAL_VERIFICATION",
            "VISUAL_CRITIQUE",
            "OPTIONAL_REPAIR",
            "FINAL_VERIFICATION",
            "ASSURANCE",
        )
    )
    with pytest.raises(ValueError):
        validate_fixed_graph(("DESIGN_BUILDER", "ASSURANCE"))
    with pytest.raises(ValueError):
        validate_fixed_graph(("DESIGN_BUILDER", "STRUCTURAL_VERIFICATION", "DESIGN_BUILDER"))


def test_builder_request_binds_host_and_context_digests(tmp_path) -> None:
    task = make_task(tmp_path)
    fingerprint = make_fingerprint(tmp_path)
    request = build_builder_request(
        task,
        fingerprint,
        host_executable_digest=HOST_DIGEST,
        host_interpreter_digest=HOST_DIGEST,
        attempt=1,
    )
    assert request.skill_name == "design-director"
    assert request.authorization.host_executable_digest == HOST_DIGEST
    assert request.context.acceptance_criteria == task.criteria.serialized
    assert request.authorization.allowed_tools == ()
    assert request.authorization.network_policy == "DENY"


def test_allowlist_mapping_rejects_unknown_fields(tmp_path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    payload = {
        "schema_version": "P5-POLICY-1",
        "builder": {
            "capability_id": fingerprint.capability_id,
            "version": fingerprint.version,
            "scope": fingerprint.scope,
            "canonical_path": fingerprint.canonical_path,
            "package_fingerprint": fingerprint.package_fingerprint,
            "manifest_fingerprint": fingerprint.manifest_fingerprint,
            "provenance": fingerprint.provenance,
            "trust": fingerprint.trust,
            "compatibility": fingerprint.compatibility,
            "package_status": fingerprint.package_status,
            "load_eligibility": fingerprint.load_eligibility,
            "files": list(fingerprint.files),
            "scripts": [],
            "dependencies": [],
        },
        "builder_manifest_fingerprint": fingerprint.manifest_fingerprint,
        "approved_status": "APPROVED_RESPONSE_ONLY",
        "unknown": True,
    }
    with pytest.raises(ValueError):
        Phase5Allowlist.from_mapping(payload)
    assert json.dumps(payload)


def test_allowlist_mapping_enforces_fixed_graph_and_budgets(tmp_path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    payload = {
        "schema_version": "P5-POLICY-1",
        "builder": fingerprint,
        "graph": ["DESIGN_BUILDER", "ASSURANCE"],
        "budgets": {"max_repairs": 9},
    }
    with pytest.raises(ValueError):
        Phase5Allowlist.from_mapping(payload)

    payload["graph"] = [
        "DESIGN_BUILDER",
        "STRUCTURAL_VERIFICATION",
        "VISUAL_CRITIQUE",
        "OPTIONAL_REPAIR",
        "FINAL_VERIFICATION",
        "ASSURANCE",
    ]
    with pytest.raises(ValueError):
        Phase5Allowlist.from_mapping({**payload, "budgets": {"max_builder_invocations": 3}})


def test_allowlist_mapping_requires_explicit_graph_and_budgets(tmp_path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    with pytest.raises(ValueError):
        Phase5Allowlist.from_mapping(
            {
                "schema_version": "P5-POLICY-1",
                "builder": fingerprint,
                "builder_manifest_fingerprint": fingerprint.manifest_fingerprint,
                "approved_status": "APPROVED_RESPONSE_ONLY",
            }
        )
