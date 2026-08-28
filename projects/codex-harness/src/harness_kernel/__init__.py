"""Project-local Phase 1 contract-first harness kernel.

The package exposes data and validation primitives only. It deliberately has no
capability executor, provider router, subprocess runner, or Skill mutator.
"""

from .models import (
    CapabilityInvocation,
    CapabilityManifest,
    ExecutionGraph,
    InstallationScope,
    RegistryOrigin,
    RouteDecision,
    RunSummary,
    TaskProfile,
)
from .serialization import from_dict, from_json, to_dict, to_json
from .validation import ValidationResult, validate

__all__ = [
    "CapabilityInvocation",
    "CapabilityManifest",
    "ExecutionGraph",
    "InstallationScope",
    "RegistryOrigin",
    "RouteDecision",
    "RunSummary",
    "TaskProfile",
    "ValidationResult",
    "from_dict",
    "from_json",
    "to_dict",
    "to_json",
    "validate",
]
