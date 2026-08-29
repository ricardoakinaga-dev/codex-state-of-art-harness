"""Trust, compatibility and staleness decisions for observed metadata."""

from __future__ import annotations

import platform
import re
import sys
from collections.abc import Iterable, Mapping

from .phase3_models import (
    CompatibilityAssessment,
    CompatibilityStatus,
    ObservationStatus,
    ObservedCapabilityManifest,
    RootScope,
    TrustAssessment,
    TrustLevel,
)

_PYTHON_LIMIT = re.compile(
    r"^python\s*(?P<operator>>=|<=|=|>|<)\s*(?P<version>\d+(?:\.\d+)*)$", re.I
)


def assess_trust(
    scope: RootScope,
    *,
    content_hash: str,
    source_repository: str = "",
    source_type: str = "LOCAL",
    known_hashes: Iterable[str] = (),
    rejected: bool = False,
) -> TrustAssessment:
    """Assign trust from bounded evidence, never from an in-package claim alone."""

    if rejected:
        return TrustAssessment(
            TrustLevel.REJECTED,
            ("package validation rejected the record",),
            None,
            "invalid or unsafe package metadata",
            ObservationStatus.OBSERVED,
        )
    if content_hash in set(known_hashes):
        return TrustAssessment(
            TrustLevel.OFFICIAL,
            ("explicit external hash allowlist",),
            None,
            "hash is present in an explicit verifier-supplied allowlist",
            ObservationStatus.OBSERVED,
        )
    if scope is RootScope.PROJECT:
        return TrustAssessment(
            TrustLevel.PROJECT_TRUSTED,
            ("project-local ownership boundary",),
            source_repository or None,
            "project ownership is trusted for local selection, not proof of safety",
            ObservationStatus.OBSERVED,
        )
    if scope in {RootScope.WORKSPACE, RootScope.VENDORED}:
        return TrustAssessment(
            TrustLevel.VERIFIED_LOCAL,
            ("workspace or vendored local boundary",),
            source_repository or None,
            "local boundary is known but package content remains untrusted data",
            ObservationStatus.OBSERVED,
        )
    if source_type.upper() == "OFFICIAL" and source_repository:
        return TrustAssessment(
            TrustLevel.UNVERIFIED,
            ("package-declared official source is not independent evidence",),
            source_repository,
            "official provenance claim requires an external verifier",
            ObservationStatus.OBSERVED,
        )
    if scope is RootScope.SYSTEM:
        return TrustAssessment(
            TrustLevel.UNVERIFIED,
            ("system path without independent package verification",),
            None,
            "system location is not treated as official by path alone",
            ObservationStatus.INFERRED,
        )
    return TrustAssessment(
        TrustLevel.THIRD_PARTY,
        ("no project or independent verification evidence",),
        source_repository or None,
        "external or global package is not automatically trusted",
        ObservationStatus.INFERRED,
    )


def host_features() -> tuple[str, ...]:
    return (
        f"python>={sys.version_info.major}.{sys.version_info.minor}",
        f"platform:{platform.system().casefold()}",
    )


def assess_compatibility(
    manifest: ObservedCapabilityManifest,
    *,
    available_features: Iterable[str] = (),
) -> CompatibilityAssessment:
    """Classify platform/host requirements without probing or executing them."""

    available = {item.casefold() for item in (*host_features(), *available_features)}
    required = tuple(manifest.platform_limits)
    missing: list[str] = []
    debt: list[str] = []
    reasons: list[str] = []
    for requirement in required:
        folded = requirement.casefold().strip()
        match = _PYTHON_LIMIT.fullmatch(folded)
        if match:
            actual = (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
            wanted = tuple(int(part) for part in match.group("version").split("."))
            wanted = (wanted + (0, 0, 0))[:3]
            operator = match.group("operator")
            passes = {
                ">=": actual >= wanted,
                "<=": actual <= wanted,
                "=": actual[: len(match.group("version").split("."))]
                == wanted[: len(match.group("version").split("."))],
                ">": actual > wanted,
                "<": actual < wanted,
            }[operator]
            if not passes:
                missing.append(requirement)
                reasons.append(f"python requirement is not met: {requirement}")
            continue
        if folded in available or folded in {item.split(":", 1)[-1] for item in available}:
            continue
        if folded.startswith(("linux", "darwin", "windows")):
            if f"platform:{folded}" not in available:
                missing.append(requirement)
                reasons.append(f"platform requirement is not observed: {requirement}")
            continue
        debt.append(f"unverified host requirement: {requirement}")

    if manifest.kind.value != "NATIVE":
        debt.append("manifest was synthesized or legacy; native host contract is not proven")
    if manifest.providers:
        debt.append("provider metadata is inventory-only in Phase 3")
    if manifest.tools:
        debt.append("tool availability is not execution authorization")
    if missing:
        status = CompatibilityStatus.INCOMPATIBLE
        confidence = ObservationStatus.OBSERVED
    elif debt:
        status = CompatibilityStatus.PARTIAL
        confidence = ObservationStatus.INFERRED
        reasons.append("requirements not represented by a verified host capability contract")
    else:
        status = CompatibilityStatus.COMPATIBLE
        confidence = ObservationStatus.OBSERVED
        reasons.append("declared platform limits match observed local runtime")
    return CompatibilityAssessment(
        status,
        required,
        tuple(missing),
        required,
        tuple(debt),
        tuple(reasons),
        confidence,
    )


def stale_for_fingerprint(observed: str, current: str) -> bool:
    """Compare declarative-input fingerprints; empty values are unknown, not fresh."""

    if not observed or not current:
        return True
    return observed != current


def redacted_claims(values: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Keep only keys useful for provenance, never arbitrary environment data."""

    allowed = {"source_repository", "upstream", "forked_from", "tag", "commit"}
    return tuple(sorted((key, value[:300]) for key, value in values.items() if key in allowed))
