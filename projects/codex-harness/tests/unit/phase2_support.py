from __future__ import annotations

from pathlib import Path

from harness_kernel.authority import AuthorityAction, AuthorityScope
from harness_kernel.boundary import ProjectBoundary
from harness_kernel.execution import ExecutionKernel


def broad_test_authority() -> AuthorityScope:
    """Explicit fixture grant for tests that exercise provider execution."""

    return AuthorityScope(
        owner="test-policy",
        actor="test-runner",
        scopes=("task:*", "capability:*"),
        decisions=(AuthorityAction.TRANSITION, AuthorityAction.REPLAN),
        subject_owner="test-policy",
        operations=("execute",),
        issued_at="1970-01-01T00:00:00Z",
        expires_at="2099-12-31T23:59:59Z",
    )


def authorized_kernel(boundary: Path | ProjectBoundary, **kwargs: object) -> ExecutionKernel:
    selected_boundary = (
        boundary if isinstance(boundary, ProjectBoundary) else ProjectBoundary(boundary)
    )
    return ExecutionKernel(selected_boundary, authority=broad_test_authority(), **kwargs)
