"""Bounded project-local contract and deterministic execution kernel.

Phase 2 adds only the explicit local provider seam and sequential executor.
There is still no shell, network, host adapter, Skill, MCP or subagent runtime.
"""

from .execution import ExecutionKernel, ExecutionLimits, ExecutionStatus, RepairRecord, RunResult
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
    "ExecutionKernel",
    "ExecutionGraph",
    "ExecutionLimits",
    "ExecutionStatus",
    "InstallationScope",
    "RegistryOrigin",
    "RouteDecision",
    "RunSummary",
    "RunResult",
    "RepairRecord",
    "TaskProfile",
    "ValidationResult",
    "from_dict",
    "from_json",
    "to_dict",
    "to_json",
    "validate",
]
