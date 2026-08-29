"""Explicit local provider contracts; providers never route or authorize work."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .classification import DEFAULT_TIMESTAMP
from .errors import FailureCategory, FailureDetail
from .models import CapabilityInvocation, CapabilityManifest, RegistryOrigin
from .serialization import to_json


class ProviderAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"


class ProviderResultStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    provider_id: str
    version: str
    capability_ids: tuple[str, ...]
    operations: tuple[str, ...]
    origin: RegistryOrigin | str = RegistryOrigin.PROJECT
    local_only: bool = True
    execution_mode: str = "FIXTURE"
    limits: tuple[tuple[str, int], ...] = ()
    security_characteristics: tuple[str, ...] = (
        "project-local",
        "non-networked",
        "non-shell",
        "non-privileged",
    )
    supports_cancellation: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provider_id, str)
            or not self.provider_id.strip()
            or not isinstance(self.version, str)
            or not self.version.strip()
        ):
            raise ValueError("provider identity is required")
        if not self.capability_ids:
            raise ValueError("provider must declare at least one capability")
        if not self.operations:
            raise ValueError("provider must declare at least one operation")
        capabilities = tuple(dict.fromkeys(self.capability_ids))
        operations = tuple(dict.fromkeys(self.operations))
        if any(
            not isinstance(item, str) or not item.strip() for item in (*capabilities, *operations)
        ):
            raise ValueError("provider capabilities and operations must be non-empty strings")
        if not isinstance(self.execution_mode, str) or not self.execution_mode.strip():
            raise ValueError("provider execution mode is required")
        if getattr(self.origin, "value", self.origin) != RegistryOrigin.PROJECT.value:
            raise ValueError("only project-origin providers are admitted")
        if not isinstance(self.local_only, bool) or not self.local_only:
            raise ValueError("only project-local providers are admitted")
        if self.execution_mode not in {"FIXTURE", "DETERMINISTIC_FIXTURE"}:
            raise ValueError("provider execution mode is outside the Phase 2 allowlist")
        if not isinstance(self.supports_cancellation, bool):
            raise ValueError("provider cancellation support must be boolean")
        limits = tuple(self.limits)
        if len({key for key, _ in limits}) != len(limits):
            raise ValueError("provider limit names must be unique")
        for key, value in limits:
            if (
                not isinstance(key, str)
                or not key.strip()
                or not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError("provider limits must be named non-negative integers")
        security = tuple(dict.fromkeys(self.security_characteristics))
        if any(not isinstance(item, str) or not item.strip() for item in security):
            raise ValueError("provider security characteristics must be non-empty strings")
        required_security = {
            "project-local",
            "non-networked",
            "non-shell",
            "non-privileged",
        }
        if not required_security.issubset(security):
            raise ValueError("provider security characteristics are insufficient for Phase 2")
        object.__setattr__(self, "capability_ids", capabilities)
        object.__setattr__(self, "operations", operations)
        object.__setattr__(self, "limits", limits)
        object.__setattr__(self, "security_characteristics", security)


@dataclass(frozen=True, slots=True)
class ProviderExecutionResult:
    """Structured provider output. It contains no routing or assurance decision."""

    provider_id: str
    invocation_id: str
    status: ProviderResultStatus | str
    output: object | None
    output_contract: str
    output_digest: str | None
    failure: FailureDetail | None = None
    duration_ms: int = 1
    attempt: int = 1
    started_at: str | None = None
    ended_at: str | None = None
    artifact_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    telemetry_refs: tuple[str, ...] = ()
    resource_observations: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provider_id, str)
            or not self.provider_id.strip()
            or not isinstance(self.invocation_id, str)
            or not self.invocation_id.strip()
        ):
            raise ValueError("provider result identity is required")
        if not isinstance(self.output_contract, str) or not self.output_contract.strip():
            raise ValueError("provider output contract is required")
        if (
            not isinstance(self.duration_ms, int)
            or isinstance(self.duration_ms, bool)
            or self.duration_ms < 0
        ):
            raise ValueError("provider duration must be a non-negative integer")
        if not isinstance(self.attempt, int) or isinstance(self.attempt, bool) or self.attempt < 1:
            raise ValueError("provider attempt must be positive")
        normalized = (
            self.status
            if isinstance(self.status, ProviderResultStatus)
            else ProviderResultStatus(str(self.status))
        )
        object.__setattr__(self, "status", normalized)
        if self.output is not None:
            expected_digest = digest_output(self.output)
            if self.output_digest is None:
                object.__setattr__(self, "output_digest", expected_digest)
            elif self.output_digest != expected_digest:
                raise ValueError("provider output digest does not match output")
        elif self.output_digest is not None:
            raise ValueError("provider output digest requires output")
        if normalized is ProviderResultStatus.FAILED and self.failure is None:
            raise ValueError("failed provider results need a typed failure")
        if normalized is ProviderResultStatus.SUCCEEDED and self.failure is not None:
            raise ValueError("successful provider results cannot carry a failure")
        for name, values in (
            ("artifact_refs", self.artifact_refs),
            ("evidence_refs", self.evidence_refs),
            ("telemetry_refs", self.telemetry_refs),
        ):
            normalized_refs = tuple(values)
            if any(not isinstance(item, str) or not item.strip() for item in normalized_refs):
                raise ValueError(f"{name} must contain non-empty strings")
            object.__setattr__(self, name, tuple(dict.fromkeys(normalized_refs)))
        observations = tuple(self.resource_observations)
        if any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not all(isinstance(part, str) and part.strip() for part in item)
            for item in observations
        ):
            raise ValueError("resource observations must be string pairs")
        object.__setattr__(self, "resource_observations", observations)


class CapabilityProvider(Protocol):
    """Minimal provider seam used by the local execution kernel."""

    @property
    def descriptor(self) -> ProviderDescriptor: ...

    def execute(
        self,
        invocation: CapabilityInvocation,
        manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult: ...


@dataclass(frozen=True, slots=True)
class ProviderRegistration:
    descriptor: ProviderDescriptor
    provider: CapabilityProvider
    availability: ProviderAvailability

    @property
    def usable(self) -> bool:
        return self.availability is ProviderAvailability.AVAILABLE


@dataclass(frozen=True, slots=True)
class ProviderInspection:
    provider_id: str
    registration: ProviderRegistration | None

    @property
    def registered(self) -> bool:
        return self.registration is not None

    @property
    def availability(self) -> ProviderAvailability:
        if self.registration is None:
            return ProviderAvailability.UNAVAILABLE
        return self.registration.availability

    @property
    def usable(self) -> bool:
        return bool(self.registration and self.registration.usable)


def digest_output(value: object) -> str:
    """Hash canonical JSON output without evaluating or importing it."""

    return f"sha256:{hashlib.sha256(to_json(value).encode('utf-8')).hexdigest()}"


def _attempt(invocation: CapabilityInvocation) -> int:
    for key, value in invocation.trace_context:
        if key == "attempt":
            try:
                parsed = int(value)
            except ValueError:
                return 1
            return max(1, parsed)
    return 1


def _fixture_observation_timestamps(invocation: CapabilityInvocation) -> tuple[str, str]:
    """Return the deterministic observation envelope supplied by a fixture."""

    observed_at = invocation.started_at or DEFAULT_TIMESTAMP
    return observed_at, observed_at


@dataclass(frozen=True, slots=True)
class DeterministicSuccessProvider:
    """A side-effect-free provider that returns a reproducible local fixture."""

    provider_id: str = "local.success"
    version: str = "1.0.0"
    duration_ms: int = 1
    delay_ms: int = 0
    result_provider_id: str | None = None
    output_contract: str = "LocalExecutionResult"
    emit_observed_timestamps: bool = True

    def __post_init__(self) -> None:
        if (
            not isinstance(self.duration_ms, int)
            or isinstance(self.duration_ms, bool)
            or self.duration_ms < 0
            or self.duration_ms > 60_000
        ):
            raise ValueError("fixture duration must be a bounded non-negative integer")
        if (
            not isinstance(self.delay_ms, int)
            or isinstance(self.delay_ms, bool)
            or self.delay_ms < 0
            or self.delay_ms > 60_000
        ):
            raise ValueError("fixture delay must be a bounded non-negative integer")
        if (
            not isinstance(self.output_contract, str)
            or self.output_contract != "LocalExecutionResult"
        ):
            raise ValueError("deterministic success fixtures use LocalExecutionResult")
        if self.result_provider_id is not None and (
            not isinstance(self.result_provider_id, str) or not self.result_provider_id.strip()
        ):
            raise ValueError("fixture result provider identity must be non-empty")
        if not isinstance(self.emit_observed_timestamps, bool):
            raise ValueError("fixture observed timestamp setting must be boolean")

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=self.provider_id,
            version=self.version,
            capability_ids=("local.direct", self.provider_id),
            operations=("execute",),
            execution_mode="DETERMINISTIC_FIXTURE",
        )

    def execute(
        self,
        invocation: CapabilityInvocation,
        manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        del manifest
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000)
        output = {
            "kind": "deterministic-local-result",
            "objective_digest": digest_output(invocation.objective),
            "operation": invocation.operation or "execute",
            "provider": self.result_provider_id or self.provider_id,
        }
        started_at, ended_at = _fixture_observation_timestamps(invocation)
        return ProviderExecutionResult(
            provider_id=self.result_provider_id or self.provider_id,
            invocation_id=invocation.invocation_id,
            status=ProviderResultStatus.SUCCEEDED,
            output=output,
            output_contract=self.output_contract,
            output_digest=digest_output(output),
            duration_ms=self.duration_ms,
            attempt=_attempt(invocation),
            started_at=started_at if self.emit_observed_timestamps else None,
            ended_at=ended_at if self.emit_observed_timestamps else None,
        )


@dataclass(frozen=True, slots=True)
class DeterministicFailureProvider:
    """A reproducible provider failure fixture for negative and repair tests."""

    provider_id: str = "local.failure"
    version: str = "1.0.0"

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=self.provider_id,
            version=self.version,
            capability_ids=("local.direct", self.provider_id),
            operations=("execute",),
            execution_mode="DETERMINISTIC_FIXTURE",
        )

    def execute(
        self,
        invocation: CapabilityInvocation,
        manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        started_at, ended_at = _fixture_observation_timestamps(invocation)
        return ProviderExecutionResult(
            provider_id=self.provider_id,
            invocation_id=invocation.invocation_id,
            status=ProviderResultStatus.FAILED,
            output=None,
            output_contract="LocalExecutionResult",
            output_digest=None,
            failure=FailureDetail(
                category=FailureCategory.PROVIDER,
                code="FIXTURE_FAILURE",
                message="deterministic provider fixture failed",
                retryable=False,
                refs=(invocation.invocation_id,),
                attempt=_attempt(invocation),
            ),
            duration_ms=1,
            attempt=_attempt(invocation),
            started_at=started_at,
            ended_at=ended_at,
        )


@dataclass(frozen=True, slots=True)
class DeterministicRetryProvider:
    """Fails a bounded number of explicit attempts, then succeeds."""

    failures_before_success: int = 1
    provider_id: str = "local.retry"
    version: str = "1.0.0"
    duration_ms: int = 1
    delay_ms: int = 0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.failures_before_success, int)
            or isinstance(self.failures_before_success, bool)
            or self.failures_before_success < 0
        ):
            raise ValueError("failures_before_success must be non-negative")
        for name, value in (("duration_ms", self.duration_ms), ("delay_ms", self.delay_ms)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 60_000:
                raise ValueError(f"fixture {name} must be a bounded non-negative integer")

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=self.provider_id,
            version=self.version,
            capability_ids=("local.direct", self.provider_id),
            operations=("execute",),
            execution_mode="DETERMINISTIC_FIXTURE",
        )

    def execute(
        self,
        invocation: CapabilityInvocation,
        manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        attempt = _attempt(invocation)
        if attempt <= self.failures_before_success:
            if self.delay_ms:
                time.sleep(self.delay_ms / 1000)
            started_at, ended_at = _fixture_observation_timestamps(invocation)
            return ProviderExecutionResult(
                provider_id=self.provider_id,
                invocation_id=invocation.invocation_id,
                status=ProviderResultStatus.FAILED,
                output=None,
                output_contract="LocalExecutionResult",
                output_digest=None,
                failure=FailureDetail(
                    category=FailureCategory.PROVIDER,
                    code="FIXTURE_RETRYABLE_FAILURE",
                    message="deterministic provider fixture requested a bounded retry",
                    retryable=True,
                    refs=(invocation.invocation_id,),
                    attempt=attempt,
                ),
                duration_ms=self.duration_ms,
                attempt=attempt,
                started_at=started_at,
                ended_at=ended_at,
            )
        return DeterministicSuccessProvider(
            self.provider_id,
            self.version,
            duration_ms=self.duration_ms,
            delay_ms=self.delay_ms,
        ).execute(invocation, manifest)


@dataclass(frozen=True, slots=True)
class DeterministicPartialProvider:
    """A deterministic provider that preserves a useful but incomplete output."""

    provider_id: str = "local.partial"
    version: str = "1.0.0"

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=self.provider_id,
            version=self.version,
            capability_ids=("local.direct", self.provider_id),
            operations=("execute",),
            execution_mode="DETERMINISTIC_FIXTURE",
        )

    def execute(
        self,
        invocation: CapabilityInvocation,
        manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        output = {
            "kind": "deterministic-local-partial-result",
            "objective_digest": digest_output(invocation.objective),
            "provider": self.provider_id,
        }
        started_at, ended_at = _fixture_observation_timestamps(invocation)
        return ProviderExecutionResult(
            provider_id=self.provider_id,
            invocation_id=invocation.invocation_id,
            status=ProviderResultStatus.PARTIAL,
            output=output,
            output_contract="LocalExecutionResult",
            output_digest=digest_output(output),
            failure=FailureDetail(
                category=FailureCategory.PROVIDER,
                code="FIXTURE_PARTIAL",
                message="deterministic provider fixture returned partial output",
                retryable=False,
                refs=(invocation.invocation_id,),
                attempt=_attempt(invocation),
            ),
            duration_ms=1,
            attempt=_attempt(invocation),
            started_at=started_at,
            ended_at=ended_at,
        )


@dataclass(frozen=True, slots=True)
class DeterministicRepairProvider(DeterministicSuccessProvider):
    """Explicit success fixture used only when a caller authorizes repair."""

    provider_id: str = "local.repair"


_BUILTIN_PROVIDER_TYPES = frozenset(
    {
        DeterministicSuccessProvider,
        DeterministicFailureProvider,
        DeterministicRetryProvider,
        DeterministicPartialProvider,
        DeterministicRepairProvider,
    }
)


@dataclass(frozen=True, slots=True)
class ProviderRegistry:
    """Immutable provider registrations with exact, explicit resolution only."""

    registrations: tuple[ProviderRegistration, ...] = ()

    def __post_init__(self) -> None:
        normalized = tuple(self.registrations)
        if any(not isinstance(item, ProviderRegistration) for item in normalized):
            raise TypeError("provider registrations must use the typed registration contract")
        if any(type(item.provider) not in _BUILTIN_PROVIDER_TYPES for item in normalized):
            raise ValueError("only built-in deterministic fixture providers are admitted")
        if any(
            item.descriptor != item.provider.descriptor
            or not isinstance(item.availability, ProviderAvailability)
            for item in normalized
        ):
            raise ValueError("provider registration metadata must match its built-in provider")
        ids = [item.descriptor.provider_id for item in normalized]
        if len(ids) != len(set(ids)):
            raise ValueError("provider IDs must be unique")
        if any(not item.descriptor.local_only for item in normalized):
            raise ValueError("only project-local providers are admitted")
        object.__setattr__(self, "registrations", normalized)

    @classmethod
    def local_defaults(cls) -> ProviderRegistry:
        return (
            cls()
            .register(DeterministicSuccessProvider())
            .register(DeterministicFailureProvider())
            .register(DeterministicRetryProvider())
            .register(DeterministicPartialProvider())
            .register(DeterministicRepairProvider())
        )

    def register(
        self,
        provider: CapabilityProvider,
        *,
        availability: ProviderAvailability = ProviderAvailability.AVAILABLE,
    ) -> ProviderRegistry:
        if type(provider) not in _BUILTIN_PROVIDER_TYPES:
            raise ValueError("only built-in deterministic fixture providers are admitted")
        descriptor = provider.descriptor
        if any(
            item.descriptor.provider_id == descriptor.provider_id for item in self.registrations
        ):
            raise ValueError("provider ID is already registered")
        return ProviderRegistry(
            registrations=(
                *self.registrations,
                ProviderRegistration(descriptor, provider, availability),
            )
        )

    def with_availability(
        self, provider_id: str, availability: ProviderAvailability
    ) -> ProviderRegistry:
        found = False
        updated: list[ProviderRegistration] = []
        for item in self.registrations:
            if item.descriptor.provider_id == provider_id:
                found = True
                updated.append(ProviderRegistration(item.descriptor, item.provider, availability))
            else:
                updated.append(item)
        if not found:
            raise KeyError("provider is not registered")
        return ProviderRegistry(tuple(updated))

    def inspect(self, provider_id: str) -> ProviderInspection:
        return ProviderInspection(
            provider_id,
            next(
                (item for item in self.registrations if item.descriptor.provider_id == provider_id),
                None,
            ),
        )

    def resolve(
        self,
        provider_id: str,
        *,
        operation: str = "execute",
        capability_id: str | None = None,
    ) -> CapabilityProvider | None:
        inspection = self.inspect(provider_id)
        registration = inspection.registration
        if registration is None or not registration.usable:
            return None
        if operation not in registration.descriptor.operations:
            return None
        if (
            capability_id is not None
            and capability_id not in registration.descriptor.capability_ids
        ):
            return None
        return registration.provider

    def providers_for(self, capability_id: str, *, operation: str = "execute") -> tuple[str, ...]:
        return tuple(
            item.descriptor.provider_id
            for item in self.registrations
            if item.usable
            and operation in item.descriptor.operations
            and capability_id in item.descriptor.capability_ids
        )


ProviderResult = ProviderExecutionResult
LocalSuccessProvider = DeterministicSuccessProvider
LocalFailureProvider = DeterministicFailureProvider
