"""Phase 8.1 frontend host adapter for one bounded composition run.

P8.1-FINDING-H-HOST-COMPOSITION-001 requires a real host-produced artifact.
This specialization reuses the hardened Phase 7 workspace-write boundary but
authenticates the exact project-local frontend package and keeps the typed
Skill input intact for the official App Server turn.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from threading import Event

from .phase4_host import AppServerClient
from .phase4_models import (
    CapabilityExecutionAuthorization,
    CapabilityInvocationRequest,
    HostInvocationResult,
    InvocationResultStatus,
    Phase4Budget,
)
from .phase7_backend import package_fingerprint, snapshot_workspace, validate_workspace_delta
from .phase7_host import (
    BackendBuilderAppServerAdapter,
    WorkspaceFilesystemPolicy,
    WorkspaceWriteMode,
    _authorization_binding_errors,
    _under,
)

FRONTEND_CAPABILITY_ID = "frontend-engineering-vnext"
VERIFIER_CAPABILITY_ID = "verification-loop-vnext"


class FrontendBuilderAppServerAdapter(BackendBuilderAppServerAdapter):
    """Allow only bounded frontend writes under an exact current package."""

    _developer_instructions = (
        "This is a Harness-controlled frontend closure pilot. The policy is authoritative. "
        "Use only the host-provided bounded list/read/write tools for files under the "
        "declared app root. Do not use shell, scripts, commands, network, MCP, providers, "
        "credentials or subagents. Do not change the capability package, control plane, "
        "application behavior, styling or acceptance criteria."
    )

    def _skill_is_discovered(  # type: ignore[override]
        self,
        response: Mapping[str, object],
        request: CapabilityInvocationRequest,
    ) -> bool:
        """Authenticate the typed frontend Skill input independently of listing text."""

        del response
        if request.skill_name != FRONTEND_CAPABILITY_ID:
            return False
        candidate = Path(request.skill_path)
        if candidate.name != "SKILL.md":
            return False
        try:
            policy = self._policy_for_request(request)
            package = policy.package_path
            if package is None or candidate.resolve(strict=True) != package / "SKILL.md":
                return False
            if any(_under(package, root) or _under(root, package) for root in policy.allowed_roots):
                return False
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            current_fingerprint = package_fingerprint(package)
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
            return False
        execution_policy = manifest.get("execution_policy")
        if not isinstance(execution_policy, Mapping):
            return False
        return (
            current_fingerprint == request.authorization.package_fingerprint
            and package.name == FRONTEND_CAPABILITY_ID
            and manifest.get("capability_id") == FRONTEND_CAPABILITY_ID
            and manifest.get("version") == request.authorization.capability_version
            and manifest.get("type") == "SPECIALIST"
            and manifest.get("role") == "SPECIALIST"
            and manifest.get("primary_type") == "SPECIALIST"
            and manifest.get("status") == "CANDIDATE"
            and manifest.get("metadata_only") is True
            and execution_policy.get("workspace_write") == "host_bounded"
            and execution_policy.get("shell") == "deny"
            and execution_policy.get("network") == "deny"
            and execution_policy.get("mcp") in {"deny", "host_observer_only"}
            and execution_policy.get("providers") == "deny"
            and execution_policy.get("credentials") == "deny"
        )


class Phase81VerifierAppServerAdapter(BackendBuilderAppServerAdapter):
    """Expose bounded evidence reads to the verifier while forbidding every write."""

    _developer_instructions = (
        "This is a Harness-controlled verification pilot. The policy is authoritative. "
        "Use only the host-provided bounded list/read tools to inspect immutable evidence "
        "under the declared artifact root. Do not use shell, scripts, commands, writes, "
        "network, MCP, providers, credentials or subagents. Independently evaluate the "
        "neutral criteria and return one bounded JSON response; PASS is not prescribed."
    )

    def __init__(
        self,
        *,
        transport_factory: Callable[[], AppServerClient] | None = None,
        filesystem_policy: WorkspaceFilesystemPolicy,
        project_root: str | Path,
        trusted_authorization: CapabilityExecutionAuthorization,
        clock: Callable[[], float] | None = None,
    ) -> None:
        super().__init__(
            transport_factory=transport_factory,
            filesystem_policy=filesystem_policy,
            project_root=project_root,
            trusted_authorization=trusted_authorization,
            clock=clock or time.time,
            max_builder_invocations=1,
            max_repairs=0,
        )

    def _skill_is_discovered(  # type: ignore[override]
        self,
        response: Mapping[str, object],
        request: CapabilityInvocationRequest,
    ) -> bool:
        del response
        if request.skill_name != VERIFIER_CAPABILITY_ID:
            return False
        candidate = Path(request.skill_path)
        if candidate.name != "SKILL.md":
            return False
        try:
            policy = self._policy_for_request(request)
            package = policy.package_path
            if package is None or candidate.resolve(strict=True) != package / "SKILL.md":
                return False
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            execution_policy = manifest.get("execution_policy")
            current_fingerprint = package_fingerprint(package)
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(execution_policy, Mapping):
            return False
        return (
            current_fingerprint == request.authorization.package_fingerprint
            and package.name == VERIFIER_CAPABILITY_ID
            and manifest.get("capability_id") == VERIFIER_CAPABILITY_ID
            and manifest.get("version") == request.authorization.capability_version
            and manifest.get("type") == "VERIFIER"
            and manifest.get("role") == "VERIFIER"
            and manifest.get("primary_type") == "VERIFIER"
            and manifest.get("status") == "CANDIDATE"
            and execution_policy.get("workspace_write") == "deny"
            and execution_policy.get("shell") == "deny"
            and execution_policy.get("network") == "deny"
            and execution_policy.get("mcp") == "deny"
            and execution_policy.get("credentials") == "deny"
        )

    def _policy_for_request(
        self, request: CapabilityInvocationRequest
    ) -> WorkspaceFilesystemPolicy:
        """Bind read tools to the already-authorized read-only workspace itself."""

        policy = self._configured_policy
        raw = request.authorization.filesystem_policy
        if policy is None or policy.mode is not WorkspaceWriteMode.READ_ONLY:
            raise ValueError("verifier policy is not read-only")
        request_workspace = Path(request.workspace).resolve(strict=True)
        declared_workspace = Path(str(raw.get("workspace", ""))).resolve(strict=True)
        declared_package = Path(str(raw.get("package_path", ""))).resolve(strict=True)
        if (
            request_workspace != policy.workspace
            or declared_workspace != policy.workspace
            or policy.allowed_roots != (policy.workspace,)
            or raw.get("mode") != WorkspaceWriteMode.READ_ONLY.value
            or raw.get("allowed_roots", ()) not in ((), [])
            or policy.package_path is None
            or declared_package != policy.package_path
            or raw.get("package_write_allowed") is not False
            or any(
                raw.get(field) != "DENY"
                for field in ("network", "shell", "mcp", "providers", "credentials")
            )
        ):
            raise ValueError("verifier read-only workspace is not authorization-bound")
        return policy

    def _validate_filesystem_policy(self, request: CapabilityInvocationRequest) -> tuple[str, ...]:
        errors = list(
            _authorization_binding_errors(request, self._trusted_authorization, self._clock)
        )
        try:
            policy = self._policy_for_request(request)
        except (OSError, TypeError, ValueError):
            errors.append("FILESYSTEM_POLICY_INVALID")
            return tuple(dict.fromkeys(errors))
        if policy.mode is not WorkspaceWriteMode.READ_ONLY:
            errors.append("VERIFIER_MUST_REMAIN_READ_ONLY")
        if not policy.allowed_roots:
            errors.append("VERIFIER_READ_ROOT_NOT_DECLARED")
        return tuple(dict.fromkeys(errors))

    @staticmethod
    def _thread_sandbox(request: CapabilityInvocationRequest) -> str:
        del request
        return "read-only"

    def _turn_sandbox_policy(self, request: CapabilityInvocationRequest) -> dict[str, object]:
        del request
        return {"type": "readOnly", "networkAccess": False}

    @staticmethod
    def _failed_result(result: HostInvocationResult, code: str) -> HostInvocationResult:
        return replace(
            result,
            status=InvocationResultStatus.FAILURE,
            execution_observed=False,
            error_code=code,
        )

    def request_invocation(
        self,
        request: CapabilityInvocationRequest,
        *,
        budget: Phase4Budget,
        cancel_event: Event | None = None,
    ) -> HostInvocationResult:
        try:
            before = snapshot_workspace(request.workspace)
        except (OSError, RuntimeError, TypeError, ValueError):
            return self._blocked_result("WORKSPACE_SNAPSHOT_UNAVAILABLE")
        result = super().request_invocation(request, budget=budget, cancel_event=cancel_event)
        try:
            delta = validate_workspace_delta(
                request.workspace,
                before,
                allowed_roots=(),
                package_path=Path(request.skill_path).parent,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return self._failed_result(result, "VERIFIER_WORKSPACE_DELTA_UNAVAILABLE")
        self.last_workspace_delta = delta
        if not delta.ok:
            return self._failed_result(result, "VERIFIER_MUTATION_OBSERVED")
        return result
