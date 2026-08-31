from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_contracts import all_records

from harness_kernel import evidence as evidence_module
from harness_kernel import phase4_evidence as phase4_evidence_module
from harness_kernel.artifacts import (
    artifact_descendants,
    propagate_stale,
    validate_artifact_lineage,
)
from harness_kernel.evidence import (
    evidence_satisfies_claim,
    mark_evidence_stale,
    validate_evidence_links,
)
from harness_kernel.phase4_evidence import (
    EvidenceError,
    EvidenceWriter,
    build_review_manifest,
    public_outcome,
    redact_paths,
    snapshot_tree,
)


def _artifact(artifact_id: str, parents: tuple[str, ...] = (), *, supersedes=None):
    base = all_records()[5]
    return replace(
        base,
        artifact_id=artifact_id,
        supersedes=supersedes,
        provenance=replace(base.provenance, parent_artifacts=parents),
    )


def test_artifact_lineage_rejects_duplicate_self_parent_and_unknown_supersession() -> None:
    root = _artifact("ART-ROOT")
    duplicate = _artifact("ART-ROOT")
    self_parent = _artifact("ART-SELF", ("ART-SELF",), supersedes="ART-MISSING")

    result = validate_artifact_lineage((root, duplicate, self_parent))

    assert not result.is_valid
    messages = {finding.message for finding in result.findings}
    assert "artifact identifiers must be unique" in messages
    assert "artifact cannot parent itself" in messages
    assert "unknown superseded artifact" in messages


def test_artifact_lineage_rejects_invalid_targets_and_reasons() -> None:
    root = _artifact("ART-ROOT")
    with pytest.raises(ValueError, match="unknown artifact"):
        artifact_descendants((root,), "ART-MISSING")
    with pytest.raises(ValueError, match="reason"):
        from harness_kernel.artifacts import mark_artifact_stale

        mark_artifact_stale(root, " ")
    cycle = (_artifact("ART-A", ("ART-B",)), _artifact("ART-B", ("ART-A",)))
    with pytest.raises(ValueError, match="lineage"):
        propagate_stale(cycle, ("ART-A",), reason="cycle")
    with pytest.raises(ValueError, match="lineage"):
        artifact_descendants(cycle, "ART-A")


def test_artifact_descendants_deduplicates_converging_breadth_first_paths() -> None:
    root = _artifact("ART-ROOT")
    left = _artifact("ART-LEFT", ("ART-ROOT",))
    right = _artifact("ART-RIGHT", ("ART-ROOT",))
    leaf = _artifact("ART-LEAF", ("ART-LEFT", "ART-RIGHT"))

    assert artifact_descendants((leaf, right, root, left), "ART-ROOT") == (
        "ART-LEFT",
        "ART-RIGHT",
        "ART-LEAF",
    )


def test_artifact_index_rejects_blank_ids() -> None:
    result = validate_artifact_lineage((SimpleNamespace(artifact_id=""),))

    assert not result.is_valid
    assert any(finding.code.value == "INVALID_ID" for finding in result.findings)


def test_evidence_private_indexes_handle_mappings_duplicates_and_blank_ids() -> None:
    invalid = SimpleNamespace(claim_id="")
    duplicate = SimpleNamespace(claim_id="CLAIM-1")
    findings = []

    indexed = evidence_module._index(
        {"first": duplicate, "second": SimpleNamespace(claim_id="CLAIM-1")},
        "claim_id",
        "$.claims",
        findings,
    )
    evidence_module._index((invalid,), "claim_id", "$.claims", findings)

    assert indexed == {"CLAIM-1": duplicate}
    assert len(findings) == 2


def test_evidence_links_cover_unlinked_pass_records_and_digest_boundaries() -> None:
    evidence = all_records()[6]
    report = all_records()[7]
    claim = report.claims[0]
    procedure = report.procedures[0]
    artifact = all_records()[5]

    no_refs_claim = replace(claim, evidence_refs=())
    no_refs_procedure = replace(procedure, evidence_refs=())
    stale_without_reason = replace(
        evidence,
        freshness=replace(evidence.freshness, status="STALE", invalidated_by=()),
    )
    missing_digest = replace(
        evidence,
        provenance=replace(evidence.provenance, content_digest=None),
    )
    wrong_digest = replace(
        evidence,
        provenance=replace(evidence.provenance, content_digest="sha256:" + "f" * 64),
    )
    wrong_source = replace(
        evidence,
        provenance=replace(evidence.provenance, source_ref="other-producer"),
    )
    unknown_artifact = replace(evidence, artifact_refs=("ART-MISSING",))

    for claims, procedures, records, artifacts in (
        ((no_refs_claim,), (procedure,), (evidence,), None),
        ((claim,), (no_refs_procedure,), (evidence,), None),
        ((claim,), (procedure,), (stale_without_reason,), None),
        ((claim,), (procedure,), (unknown_artifact,), (artifact,)),
        ((claim,), (procedure,), (missing_digest,), (artifact,)),
        ((claim,), (procedure,), (wrong_digest,), (artifact,)),
        ((claim,), (procedure,), (wrong_source,), (artifact,)),
    ):
        result = validate_evidence_links(
            {item.claim_id: item for item in claims},
            {item.procedure_id: item for item in procedures},
            {item.evidence_id: item for item in records},
            artifacts=artifacts,
        )
        assert not result.is_valid


def test_evidence_links_cover_unknown_and_mismatched_relationships() -> None:
    evidence = all_records()[6]
    report = all_records()[7]
    claim = report.claims[0]
    procedure = report.procedures[0]

    unknown_procedure = replace(
        evidence,
        procedure=replace(evidence.procedure, procedure_id="PROC-MISSING"),
    )
    mismatched_procedure_ref = replace(
        procedure,
        evidence_refs=(evidence.evidence_id,),
    )
    mismatched_evidence = replace(
        evidence,
        procedure=replace(evidence.procedure, procedure_id="PROC-OTHER"),
    )
    result = validate_evidence_links(
        (claim,),
        (procedure, mismatched_procedure_ref),
        (unknown_procedure, mismatched_evidence),
    )

    assert not result.is_valid
    assert any("unknown procedure" in finding.message for finding in result.findings)
    assert any("does not match" in finding.message for finding in result.findings)


def test_evidence_links_reject_unknown_claim_and_procedure_references() -> None:
    evidence = all_records()[6]
    report = all_records()[7]
    claim = replace(report.claims[0], evidence_refs=("EVID-MISSING",))
    procedure = replace(report.procedures[0], evidence_refs=("EVID-MISSING",))
    result = validate_evidence_links((claim,), (procedure,), (evidence,))

    assert not result.is_valid
    assert sum("unknown evidence" in finding.message for finding in result.findings) >= 2


def test_evidence_links_accepts_non_passing_claim_without_pass_evidence_requirement() -> None:
    evidence = all_records()[6]
    report = all_records()[7]
    claim = replace(report.claims[0], status="FAIL", evidence_refs=())

    result = validate_evidence_links((claim,), (report.procedures[0],), (evidence,))

    assert not result.is_valid
    assert any("not linked" in finding.message for finding in result.findings)


def test_evidence_satisfaction_and_staling_fail_closed() -> None:
    evidence = all_records()[6]
    report = all_records()[7]
    claim = report.claims[0]
    procedure = report.procedures[0]

    assert not evidence_satisfies_claim(replace(claim, status="FAIL"), (procedure,), (evidence,))
    with pytest.raises(ValueError, match="reason"):
        mark_evidence_stale(evidence, " ", None)  # type: ignore[arg-type]


def test_evidence_private_observation_and_freshness_edges() -> None:
    evidence = all_records()[6]
    report = all_records()[7]
    assert not evidence_module._concrete_observation("")
    stale_without_reason = replace(
        evidence,
        freshness=replace(evidence.freshness, status="STALE", invalidated_by=()),
    )
    result = validate_evidence_links(
        (report.claims[0],),
        (report.procedures[0],),
        (stale_without_reason,),
    )
    assert not result.is_valid
    with_reason = replace(
        evidence,
        freshness=replace(evidence.freshness, status="STALE", invalidated_by=("changed",)),
    )
    assert (
        validate_evidence_links(
            (report.claims[0],),
            (report.procedures[0],),
            (with_reason,),
        ).is_valid
        is False
    )
    fresh_with_reason = replace(
        evidence,
        freshness=replace(evidence.freshness, status="FRESH", invalidated_by=("changed",)),
    )
    assert (
        validate_evidence_links(
            (report.claims[0],),
            (report.procedures[0],),
            (fresh_with_reason,),
        ).is_valid
        is False
    )


def test_phase4_evidence_writer_rejects_invalid_root_payload_and_bytes(tmp_path: Path) -> None:
    with pytest.raises(EvidenceError, match="absolute"):
        EvidenceWriter("relative-root")
    writer = EvidenceWriter(tmp_path / "evidence")
    with pytest.raises(EvidenceError, match="invalid"):
        writer.write_text("bad.txt", "contains\x00nul")
    with pytest.raises(EvidenceError, match="invalid"):
        writer.write_bytes("bad.bin", bytearray(b"wrong"))  # type: ignore[arg-type]
    with pytest.raises(EvidenceError, match="exceeds"):
        writer.write_bytes("large.bin", b"123", max_bytes=2)
    with pytest.raises(EvidenceError, match="relative"):
        phase4_evidence_module._safe_relative(writer.root, "/absolute.txt")
    with pytest.raises(EvidenceError, match="relative"):
        phase4_evidence_module._safe_relative(writer.root, "bad\x00name")


def test_phase4_evidence_redaction_and_relative_scope_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (
        phase4_evidence_module._redact_string(str(tmp_path), workspace=tmp_path, home=None)
        == "$WORKSPACE"
    )
    assert phase4_evidence_module._redact_string("plain", workspace=None, home=None) == "plain"
    assert redact_paths(42) == 42
    root = tmp_path / "evidence"
    root.mkdir()
    monkeypatch.setattr(Path, "is_relative_to", lambda _self, _other: False)
    with pytest.raises(EvidenceError, match="escapes"):
        phase4_evidence_module._safe_relative(root, "safe.txt")


def test_phase4_evidence_public_outcome_accepts_object_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(phase4_evidence_module, "public_data", lambda _value: {})
    assert public_outcome(object())["schema_version"] == "P4-OUTCOME-1"  # type: ignore[arg-type]


def test_phase4_evidence_writer_handles_root_creation_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_lstat(_self: Path):
        raise FileNotFoundError

    monkeypatch.setattr(Path, "lstat", missing_lstat)
    with pytest.raises(EvidenceError, match="cannot be created"):
        EvidenceWriter("/missing-evidence-root")


def test_phase4_evidence_writer_detects_directory_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "evidence"
    writer = EvidenceWriter(root)
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    target_parent = root / "reports"
    original_lstat = Path.lstat

    def changed_lstat(path: Path):
        if path == target_parent:
            return replacement.lstat()
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", changed_lstat)
    with pytest.raises(EvidenceError, match="changed during write"):
        writer.write_bytes("reports/result.txt", b"result")


def test_phase4_evidence_manifest_rejects_unavailable_and_untrusted_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    writer = EvidenceWriter(root)
    writer.write_text("ok.txt", "ok")
    with pytest.raises(EvidenceError, match="unavailable"):
        build_review_manifest(root, ("missing.txt",))
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(EvidenceError, match="label"):
        build_review_manifest(root, ("ok.txt",), bound_files=(("../outside.txt", outside),))
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    with pytest.raises(EvidenceError, match="not regular"):
        build_review_manifest(root, (), bound_files=(("link.txt", link),))
    with pytest.raises(EvidenceError, match="label"):
        build_review_manifest(root, (), bound_files=(("", outside),))


def test_phase4_evidence_snapshot_covers_root_types_and_truncation(tmp_path: Path) -> None:
    regular_one = tmp_path / "one.txt"
    regular_two = tmp_path / "two.txt"
    regular_one.write_text("one", encoding="utf-8")
    regular_two.write_text("two", encoding="utf-8")
    symlink = tmp_path / "link"
    symlink.symlink_to(regular_one)
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    try:
        with pytest.raises(EvidenceError, match="bound"):
            snapshot_tree((tmp_path,), max_entries=0)
        snapshot = snapshot_tree((regular_one, regular_two, symlink, fifo), max_entries=1)
        statuses = {item["status"] for item in snapshot["roots"]}
        assert statuses == {"OBSERVED_FILE", "SYMLINK_REJECTED", "NOT_DIRECTORY"}
        assert snapshot["truncated"] is True
    finally:
        fifo.unlink()


def test_phase4_evidence_snapshot_records_symlinks_and_scandir_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "target.txt"
    target.write_text("target", encoding="utf-8")
    link = root / "link.txt"
    link.symlink_to(target)
    snapshot = snapshot_tree((root,))
    assert any(item["status"] == "SYMLINK_NOT_FOLLOWED" for item in snapshot["entries"])

    original_scandir = phase4_evidence_module.os.scandir

    def fail_scandir(path):
        if Path(path) == root:
            raise OSError("scandir failed")
        return original_scandir(path)

    monkeypatch.setattr(phase4_evidence_module.os, "scandir", fail_scandir)
    first = tmp_path / "first.txt"
    first.write_text("first", encoding="utf-8")
    unbounded = snapshot_tree((root,))
    assert unbounded["entry_count"] == 1
    failed = snapshot_tree((first, root), max_entries=1)
    assert failed["truncated"] is True


def test_phase4_evidence_snapshot_records_unreadable_children_and_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    class BrokenEntry:
        name = "broken"
        path = str(root / "broken")

        def stat(self, *, follow_symlinks=False):
            raise OSError("stat failed")

    monkeypatch.setattr(phase4_evidence_module.os, "scandir", lambda _path: [BrokenEntry()])
    first = tmp_path / "first.txt"
    first.write_text("first", encoding="utf-8")
    snapshot = snapshot_tree((root,), max_entries=4)
    assert any(item["status"] == "UNAVAILABLE" for item in snapshot["entries"])
    bounded = snapshot_tree((first, root), max_entries=1)
    assert bounded["truncated"] is True


def test_phase4_evidence_public_serialization_and_redaction_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert redact_paths("$HOME=/tmp/token", workspace=None).startswith("$HOME=")
    assert redact_paths({"api_key": "private", "values": ["plain"]}) == {
        "api_key": "[REDACTED]",
        "values": ["plain"],
    }
    monkeypatch.setattr(phase4_evidence_module, "public_data", lambda _value: [])
    with pytest.raises(EvidenceError, match="object"):
        public_outcome(object())  # type: ignore[arg-type]


def test_phase4_evidence_review_manifest_rejects_symlink_payload(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    EvidenceWriter(root)
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    (root / "link.txt").symlink_to(source)
    with pytest.raises(EvidenceError, match="unavailable"):
        build_review_manifest(root, ("link.txt",))


def test_phase4_evidence_snapshot_not_directory_root_is_explicit(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("target", encoding="utf-8")
    assert snapshot_tree((target,))["roots"] == [{"root": str(target), "status": "OBSERVED_FILE"}]
