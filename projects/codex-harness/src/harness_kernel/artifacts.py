"""Pure artifact lineage, DAG, and stale-propagation primitives."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import replace

from .models import ArtifactRecord, RecordStatus
from .validation import ValidationCode, ValidationFinding, ValidationResult, validate


def _items[T](values: Iterable[T] | Mapping[str, T]) -> tuple[T, ...]:
    return tuple(values.values()) if isinstance(values, Mapping) else tuple(values)


def _finding(code: ValidationCode, path: str, message: str) -> ValidationFinding:
    return ValidationFinding(code=code, path=path, message=message)


def _ordered_records(
    values: Iterable[ArtifactRecord] | Mapping[str, ArtifactRecord],
) -> tuple[ArtifactRecord, ...]:
    return tuple(sorted(_items(values), key=lambda item: item.artifact_id))


def _index(
    records: Iterable[ArtifactRecord] | Mapping[str, ArtifactRecord],
    findings: list[ValidationFinding],
) -> dict[str, ArtifactRecord]:
    indexed: dict[str, ArtifactRecord] = {}
    for index, artifact in enumerate(_ordered_records(records)):
        artifact_id = getattr(artifact, "artifact_id", None)
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            findings.append(
                _finding(
                    ValidationCode.INVALID_ID,
                    f"$.artifacts[{index}].artifact_id",
                    "artifact identifier is required",
                )
            )
            continue
        if artifact_id in indexed:
            findings.append(
                _finding(
                    ValidationCode.INVARIANT_VIOLATION,
                    f"$.artifacts[{index}].artifact_id",
                    "artifact identifiers must be unique",
                )
            )
            continue
        indexed[artifact_id] = artifact
    return indexed


def validate_artifact_lineage(
    records: Iterable[ArtifactRecord] | Mapping[str, ArtifactRecord],
) -> ValidationResult:
    """Validate parent references and acyclicity of an artifact collection."""

    findings: list[ValidationFinding] = []
    indexed = _index(records, findings)
    parents: dict[str, tuple[str, ...]] = {}
    for artifact_id, artifact in sorted(indexed.items()):
        findings.extend(validate(artifact).findings)
        parent_refs = tuple(artifact.provenance.parent_artifacts)
        parents[artifact_id] = parent_refs
        for parent_id in parent_refs:
            if parent_id == artifact_id:
                findings.append(
                    _finding(
                        ValidationCode.INVARIANT_VIOLATION,
                        f"$.artifacts[{artifact_id}].provenance.parent_artifacts",
                        "artifact cannot parent itself",
                    )
                )
            elif parent_id not in indexed:
                findings.append(
                    _finding(
                        ValidationCode.INVALID_REFERENCE,
                        f"$.artifacts[{artifact_id}].provenance.parent_artifacts",
                        "unknown parent artifact",
                    )
                )
        supersedes = artifact.supersedes
        if supersedes is not None and supersedes not in indexed:
            findings.append(
                _finding(
                    ValidationCode.INVALID_REFERENCE,
                    f"$.artifacts[{artifact_id}].supersedes",
                    "unknown superseded artifact",
                )
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(artifact_id: str) -> bool:
        if artifact_id in visiting:
            return True
        if artifact_id in visited:
            return False
        visiting.add(artifact_id)
        has_cycle = any(
            parent in indexed and visit(parent) for parent in sorted(parents.get(artifact_id, ()))
        )
        visiting.remove(artifact_id)
        visited.add(artifact_id)
        return has_cycle

    if any(visit(artifact_id) for artifact_id in sorted(indexed)):
        findings.append(
            _finding(
                ValidationCode.INVARIANT_VIOLATION,
                "$.artifacts",
                "artifact lineage must be acyclic",
            )
        )
    return ValidationResult(
        valid=not findings, findings=tuple(findings), record_type="ArtifactLineage"
    )


def artifact_descendants(
    records: Iterable[ArtifactRecord] | Mapping[str, ArtifactRecord],
    artifact_id: str,
) -> tuple[str, ...]:
    """Return descendants in deterministic breadth-first lineage order."""

    items = _items(records)
    indexed = {artifact.artifact_id: artifact for artifact in items}
    if artifact_id not in indexed:
        raise ValueError("unknown artifact invalidation target")
    result = validate_artifact_lineage(items)
    if not result.is_valid:
        raise ValueError("artifact lineage is invalid")
    children: dict[str, list[str]] = {key: [] for key in indexed}
    for child in indexed.values():
        for parent in child.provenance.parent_artifacts:
            children[parent].append(child.artifact_id)
    queue: deque[str] = deque(sorted(children[artifact_id]))
    discovered: set[str] = set()
    descendants: list[str] = []
    while queue:
        current = queue.popleft()
        if current in discovered:
            continue
        discovered.add(current)
        descendants.append(current)
        queue.extend(sorted(children[current]))
    return tuple(descendants)


def mark_artifact_stale(artifact: ArtifactRecord, reason: str) -> ArtifactRecord:
    """Return a stale copy of an artifact, preserving its artifact lifecycle."""

    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("stale reason is required")
    limitation = reason.strip()
    limitations = tuple(dict.fromkeys((*artifact.limitations, limitation)))
    envelope = replace(artifact.record, status=RecordStatus.STALE)
    return replace(artifact, record=envelope, limitations=limitations)


def propagate_stale(
    records: Iterable[ArtifactRecord] | Mapping[str, ArtifactRecord],
    invalidated_ids: Iterable[str],
    *,
    reason: str,
) -> tuple[ArtifactRecord, ...]:
    """Mark selected artifacts and every descendant stale without mutation."""

    items = _items(records)
    indexed = {artifact.artifact_id: artifact for artifact in items}
    lineage = validate_artifact_lineage(items)
    if not lineage.is_valid:
        raise ValueError("artifact lineage is invalid")
    targets = tuple(dict.fromkeys(invalidated_ids))
    unknown = [target for target in targets if target not in indexed]
    if unknown:
        raise ValueError("unknown artifact invalidation target")
    affected = set(targets)
    for target in targets:
        affected.update(artifact_descendants(items, target))
    return tuple(
        mark_artifact_stale(artifact, reason) if artifact.artifact_id in affected else artifact
        for artifact in items
    )


def is_artifact_lineage_valid(
    records: Iterable[ArtifactRecord] | Mapping[str, ArtifactRecord],
) -> bool:
    return bool(validate_artifact_lineage(records).is_valid)


validate_lineage = validate_artifact_lineage
mark_descendants_stale = propagate_stale
