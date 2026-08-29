from __future__ import annotations

from harness_kernel.phase3_models import (
    CapabilityKind,
    ObservationStatus,
    ObservedCapabilityManifest,
    RootScope,
    TrustLevel,
)
from harness_kernel.phase3_trust import assess_compatibility, assess_trust, stale_for_fingerprint


def manifest(
    *, limits: tuple[str, ...] = (), kind: CapabilityKind = CapabilityKind.NATIVE
) -> ObservedCapabilityManifest:
    return ObservedCapabilityManifest(
        "P3-CM-1",
        "demo",
        "Demo",
        "1.0.0",
        kind,
        "demo",
        "SPECIALIST",
        (),
        (),
        (),
        (),
        (),
        (),
        (),
        (),
        limits,
    )


def test_declared_official_claim_is_not_independent_trust() -> None:
    trust = assess_trust(
        RootScope.GLOBAL,
        content_hash="sha256:" + "a" * 64,
        source_repository="https://fake.example/openai/skill",
        source_type="OFFICIAL",
    )

    assert trust.level is TrustLevel.UNVERIFIED
    assert trust.confidence is ObservationStatus.OBSERVED


def test_unsupported_python_is_incompatible_and_unknown_is_debt() -> None:
    incompatible = assess_compatibility(manifest(limits=("Python >= 99.0",)))
    partial = assess_compatibility(manifest(limits=("codex.experimental.feature",)))

    assert incompatible.status.value == "INCOMPATIBLE"
    assert partial.status.value == "PARTIAL"
    assert partial.portability_debt


def test_stale_fingerprint_is_fail_closed() -> None:
    assert stale_for_fingerprint("sha256:a", "sha256:b") is True
    assert stale_for_fingerprint("", "sha256:b") is True
    assert stale_for_fingerprint("sha256:a", "sha256:a") is False
