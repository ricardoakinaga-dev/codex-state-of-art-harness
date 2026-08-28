from __future__ import annotations

from dataclasses import replace

import pytest
from test_contracts import all_records

from harness_kernel.artifacts import (
    artifact_descendants,
    propagate_stale,
    validate_artifact_lineage,
)
from harness_kernel.models import RecordStatus


def artifact_with(artifact_id: str, parents: tuple[str, ...] = ()):
    artifact = all_records()[5]
    return replace(
        artifact,
        artifact_id=artifact_id,
        provenance=replace(artifact.provenance, parent_artifacts=parents),
    )


def test_artifact_lineage_is_a_deterministic_parent_dag() -> None:
    root = artifact_with("ART-ROOT")
    child = artifact_with("ART-CHILD", (root.artifact_id,))
    grandchild = artifact_with("ART-GRANDCHILD", (child.artifact_id,))

    result = validate_artifact_lineage((grandchild, root, child))

    assert result.is_valid
    assert artifact_descendants((grandchild, root, child), root.artifact_id) == (
        "ART-CHILD",
        "ART-GRANDCHILD",
    )


def test_artifact_lineage_rejects_unknown_parents_and_cycles() -> None:
    orphan = artifact_with("ART-ORPHAN", ("ART-MISSING",))
    first = artifact_with("ART-FIRST", ("ART-SECOND",))
    second = artifact_with("ART-SECOND", ("ART-FIRST",))

    result = validate_artifact_lineage((orphan, first, second))

    assert not result.is_valid
    messages = {finding.message for finding in result.findings}
    assert "unknown parent artifact" in messages
    assert "artifact lineage must be acyclic" in messages


def test_stale_propagation_returns_new_records_without_mutating_input() -> None:
    root = artifact_with("ART-ROOT")
    child = artifact_with("ART-CHILD", (root.artifact_id,))
    grandchild = artifact_with("ART-GRANDCHILD", (child.artifact_id,))
    records = (root, child, grandchild)

    updated = propagate_stale(records, (root.artifact_id,), reason="root digest changed")

    assert records[0].record.status is RecordStatus.CURRENT
    assert tuple(item.record.status for item in updated) == (
        RecordStatus.STALE,
        RecordStatus.STALE,
        RecordStatus.STALE,
    )
    assert all("root digest changed" in item.limitations for item in updated)


def test_stale_propagation_rejects_an_unknown_invalidation_target() -> None:
    with pytest.raises(ValueError, match="unknown artifact"):
        propagate_stale((artifact_with("ART-ROOT"),), ("ART-MISSING",), reason="changed")
