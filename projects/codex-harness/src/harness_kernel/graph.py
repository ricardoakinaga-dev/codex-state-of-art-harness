"""Bounded deterministic graph validation and sequential scheduling."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .authority import AuthorityScope, check_invocation_authority
from .errors import FailureCategory, FailureDetail
from .models import ExecutionGraph, ExecutionNode, GraphStatus, InvocationStatus
from .validation import ValidationCode, ValidationFinding, ValidationResult, validate


class GraphValidationError(ValueError):
    """Raised when a graph cannot be safely scheduled."""

    def __init__(self, result: ValidationResult) -> None:
        self.result = result
        super().__init__("execution graph is invalid")


def _finding(path: str, message: str) -> ValidationFinding:
    return ValidationFinding(ValidationCode.INVARIANT_VIOLATION, message, path)


def _cancel_requested(cancelled: bool | Callable[[], bool]) -> bool:
    """Treat a failing cancellation predicate as a safe cancellation signal."""

    if not callable(cancelled):
        return bool(cancelled)
    try:
        return bool(cancelled())
    except Exception:  # noqa: BLE001 - cancellation must fail closed
        return True


def _normalized_failure(node_id: str, status: InvocationStatus) -> FailureDetail | None:
    """Give externally returned terminal node states a safe typed cause."""

    categories = {
        InvocationStatus.FAILED: (FailureCategory.PROVIDER, "NODE_EXECUTION_FAILED"),
        InvocationStatus.PARTIAL: (FailureCategory.PROVIDER, "NODE_PARTIAL"),
        InvocationStatus.BLOCKED: (FailureCategory.DEPENDENCY_FAILED, "NODE_BLOCKED"),
        InvocationStatus.CANCELLED: (FailureCategory.CANCELLED, "NODE_CANCELLED"),
        InvocationStatus.TIMED_OUT: (FailureCategory.TIMEOUT, "NODE_TIMEOUT"),
    }
    item = categories.get(status)
    if item is None:
        return None
    category, code = item
    return FailureDetail(
        category=category,
        code=code,
        message="graph node returned a terminal non-success state",
        refs=(node_id,),
    )


def _all_edges(graph: ExecutionGraph) -> tuple[tuple[str, str], ...]:
    dependencies = tuple(
        (dependency, node.node_id) for node in graph.nodes for dependency in node.depends_on
    )
    explicit = tuple((edge.from_node, edge.to_node) for edge in graph.edges)
    return (*dependencies, *explicit)


def validate_execution_graph(
    graph: object,
    *,
    max_nodes: int | None = 128,
    authority: AuthorityScope | None = None,
    required_conditions: Iterable[str] = (),
    at: str | None = None,
) -> ValidationResult:
    """Validate graph structure, budgets, ownership and optional authority."""

    findings = list(validate(graph).findings)
    if not isinstance(graph, ExecutionGraph):
        return ValidationResult(False, tuple(findings), "ExecutionGraph")
    if max_nodes is not None and (
        not isinstance(max_nodes, int) or isinstance(max_nodes, bool) or max_nodes < 1
    ):
        findings.append(_finding("$.nodes", "max_nodes must be a positive integer or null"))
    elif max_nodes is not None and len(graph.nodes) > max_nodes:
        findings.append(_finding("$.nodes", "graph exceeds its node budget"))
    node_ids = [node.node_id for node in graph.nodes]
    if len(node_ids) != len(set(node_ids)):
        findings.append(_finding("$.nodes", "node identifiers must be unique"))
    node_index = {node.node_id: node for node in graph.nodes}
    edge_pairs = _all_edges(graph)
    if len(edge_pairs) != len(set(edge_pairs)):
        findings.append(_finding("$.edges", "dependency and explicit edges must not duplicate"))
    for node in graph.nodes:
        if len(node.depends_on) != len(set(node.depends_on)):
            findings.append(_finding("$.nodes[].depends_on", "node dependencies must be unique"))
        if not node.acceptance_refs:
            findings.append(
                _finding("$.nodes[].acceptance_refs", "every executable node needs acceptance refs")
            )
        if node.provider_id is not None and not node.provider_id.strip():
            findings.append(_finding("$.nodes[].provider_id", "provider ID cannot be blank"))
        for reference in node.artifact_refs:
            if not reference.strip():
                findings.append(
                    _finding("$.nodes[].artifact_refs", "artifact refs cannot be blank")
                )
        if node.budget.tokens is not None and node.budget.tokens < 0:
            findings.append(_finding("$.nodes[].budget.tokens", "node tokens must be non-negative"))
        if node.budget.duration_ms is not None and node.budget.duration_ms < 0:
            findings.append(
                _finding("$.nodes[].budget.duration_ms", "node duration must be non-negative")
            )
    for source, target in edge_pairs:
        if source == target:
            findings.append(_finding("$.edges", "graph cannot contain self-edges"))
        if source not in node_index or target not in node_index:
            findings.append(_finding("$.edges", "graph contains a dangling edge"))
    if not graph.graph_owner.strip():
        findings.append(_finding("$.graph_owner", "graph owner is required"))
    graph_status = getattr(graph.graph_status, "value", graph.graph_status)
    if graph_status not in {item.value for item in GraphStatus}:
        findings.append(_finding("$.graph_status", "graph status is invalid"))
    elif graph_status in {
        GraphStatus.RUNNING.value,
        GraphStatus.PARTIAL.value,
        GraphStatus.BLOCKED.value,
        GraphStatus.COMPLETED.value,
        GraphStatus.CANCELLED.value,
    }:
        findings.append(_finding("$.graph_status", "terminal graph cannot be replayed"))
    for node in graph.nodes:
        node_status = getattr(node.node_status, "value", node.node_status)
        if node_status not in {
            InvocationStatus.REQUESTED.value,
            InvocationStatus.CREATED.value,
        }:
            findings.append(
                _finding(
                    f"$.nodes[{node.node_id}].node_status",
                    "terminal or active graph nodes cannot be replayed",
                )
            )
    if graph_status in {"READY", "RUNNING"} and not graph.acceptance_refs:
        findings.append(_finding("$.acceptance_refs", "ready graph needs acceptance refs"))
    if graph.graph_budget is not None:
        if graph.graph_budget.tokens is not None and graph.graph_budget.tokens < 0:
            findings.append(_finding("$.graph_budget.tokens", "graph tokens must be non-negative"))
        if graph.graph_budget.duration_ms is not None and graph.graph_budget.duration_ms < 0:
            findings.append(
                _finding("$.graph_budget.duration_ms", "graph duration must be non-negative")
            )
        token_total = sum(node.budget.tokens or 0 for node in graph.nodes)
        duration_total = sum(node.budget.duration_ms or 0 for node in graph.nodes)
        if graph.graph_budget.tokens is not None and token_total > graph.graph_budget.tokens:
            findings.append(
                _finding("$.graph_budget.tokens", "node token budgets exceed graph budget")
            )
        if (
            graph.graph_budget.duration_ms is not None
            and duration_total > graph.graph_budget.duration_ms
        ):
            findings.append(
                _finding("$.graph_budget.duration_ms", "node duration budgets exceed graph budget")
            )
    merge_ids = [item.node_id for item in graph.merge_points]
    if any(item not in node_index for item in merge_ids):
        findings.append(_finding("$.merge_points", "merge point must reference a graph node"))
    if len(merge_ids) != len(set(merge_ids)):
        findings.append(_finding("$.merge_points", "merge points must be unique"))
    if len(graph.conflict_refs) != len(set(graph.conflict_refs)):
        findings.append(_finding("$.conflict_refs", "conflict references must be unique"))
    if graph.conflict_refs and not graph.merge_points:
        findings.append(
            _finding("$.conflict_refs", "unresolved conflicts require an explicit merge point")
        )
    merge_policy = getattr(graph.merge_policy, "value", graph.merge_policy)
    if merge_policy not in {"PRESERVE_AND_ESCALATE", "BLOCK", "DROP_WITH_REASON"}:
        findings.append(_finding("$.merge_policy", "merge policy is invalid"))
    if any(not isinstance(node.allow_failed_dependencies, bool) for node in graph.nodes):
        findings.append(
            _finding("$.nodes[].allow_failed_dependencies", "dependency tolerance must be boolean")
        )
    if authority is not None:
        for node in sorted(graph.nodes, key=lambda item: item.node_id):
            check = check_invocation_authority(
                authority,
                task_id=graph.task_id,
                invocation_id=f"INV-{graph.run_id}-{node.node_id}",
                capability_id=node.capability_id,
                operation="execute",
                required_scope=(f"task:{graph.task_id}", f"capability:{node.capability_id}"),
                at=at or graph.created_at,
                required_conditions=required_conditions,
            )
            if not check.allowed:
                findings.append(
                    _finding(
                        f"$.nodes[{node.node_id}]",
                        f"node authority denied: {check.code}",
                    )
                )
    order: tuple[str, ...] = ()
    if not findings:
        order = _topological_order(graph)
        if not order:
            findings.append(_finding("$.edges", "execution graph must be acyclic"))
    return ValidationResult(not findings, tuple(findings), "ExecutionGraph")


def _topological_order(graph: ExecutionGraph) -> tuple[str, ...]:
    node_ids = {node.node_id for node in graph.nodes}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    incoming: dict[str, int] = {node_id: 0 for node_id in node_ids}
    for source, target in _all_edges(graph):
        if source not in node_ids or target not in node_ids or source == target:
            return ()
        if target not in outgoing[source]:
            outgoing[source].add(target)
            incoming[target] += 1
    ready = sorted(node_id for node_id, count in incoming.items() if count == 0)
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for child in sorted(outgoing[current]):
            incoming[child] -= 1
            if incoming[child] == 0:
                ready.append(child)
                ready.sort()
    return tuple(order) if len(order) == len(node_ids) else ()


def topological_order(graph: ExecutionGraph) -> tuple[str, ...]:
    """Return a stable order or raise before any node can execute."""

    result = validate_execution_graph(graph)
    if not result.is_valid:
        raise GraphValidationError(result)
    return _topological_order(graph)


@dataclass(frozen=True, slots=True)
class GraphNodeResult:
    node_id: str
    status: InvocationStatus
    value: object | None = None
    failure: FailureDetail | None = None
    blocked_by: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized = (
            self.status
            if isinstance(self.status, InvocationStatus)
            else InvocationStatus(str(self.status))
        )
        object.__setattr__(self, "status", normalized)
        object.__setattr__(self, "blocked_by", tuple(dict.fromkeys(self.blocked_by)))


def execute_graph(
    graph: ExecutionGraph,
    invoke: Callable[[ExecutionNode], object],
    *,
    max_nodes: int | None = 128,
    max_invocations: int | None = None,
    max_duration_ms: int | None = None,
    cancelled: bool | Callable[[], bool] = False,
) -> tuple[GraphNodeResult, ...]:
    """Execute a validated graph sequentially and block failed descendants."""

    result = validate_execution_graph(graph, max_nodes=max_nodes)
    if not result.is_valid:
        raise GraphValidationError(result)
    indexed = {node.node_id: node for node in graph.nodes}
    outcomes: dict[str, GraphNodeResult] = {}
    if max_invocations is not None and (
        not isinstance(max_invocations, int)
        or isinstance(max_invocations, bool)
        or max_invocations < 0
    ):
        raise ValueError("max_invocations must be a non-negative integer or null")
    if max_duration_ms is not None and (
        not isinstance(max_duration_ms, int)
        or isinstance(max_duration_ms, bool)
        or max_duration_ms < 0
    ):
        raise ValueError("max_duration_ms must be a non-negative integer or null")
    started = time.monotonic()
    invocation_count = 0
    merge_points = {item.node_id: item for item in graph.merge_points}
    # Validation above already applied the caller's node limit.  Calling the
    # public helper here would reapply its conservative default (128) and make
    # a valid caller-supplied 129+ node graph fail during scheduling.
    order = _topological_order(graph)
    for node_id in order:
        node = indexed[node_id]
        dependencies = tuple(node.depends_on) + tuple(
            edge.from_node for edge in graph.edges if edge.to_node == node_id
        )
        failed = tuple(
            dependency
            for dependency in sorted(set(dependencies))
            if outcomes.get(
                dependency, GraphNodeResult(dependency, InvocationStatus.BLOCKED)
            ).status
            is not InvocationStatus.SUCCEEDED
        )
        if failed and not node.allow_failed_dependencies:
            outcomes[node_id] = GraphNodeResult(
                node_id,
                InvocationStatus.BLOCKED,
                failure=FailureDetail(
                    category=FailureCategory.DEPENDENCY_FAILED,
                    code="DEPENDENCY_FAILED",
                    message="a required graph dependency did not succeed",
                    refs=failed,
                ),
                blocked_by=failed,
            )
            continue
        merge_point = merge_points.get(node_id)
        if merge_point is not None and graph.conflict_refs:
            policy = getattr(merge_point.unresolved_policy, "value", merge_point.unresolved_policy)
            code = (
                "MERGE_CONFLICT_DROPPED"
                if policy == "DROP_WITH_REASON"
                else "MERGE_CONFLICT_UNRESOLVED"
            )
            status = (
                InvocationStatus.PARTIAL
                if policy == "DROP_WITH_REASON"
                else InvocationStatus.BLOCKED
            )
            outcomes[node_id] = GraphNodeResult(
                node_id,
                status,
                failure=FailureDetail(
                    category=FailureCategory.DEPENDENCY_FAILED,
                    code=code,
                    message=(
                        "merge conflict was dropped under the declared policy"
                        if policy == "DROP_WITH_REASON"
                        else "merge conflict remained unresolved under the declared policy"
                    ),
                    refs=tuple(graph.conflict_refs),
                ),
            )
            continue
        is_cancelled = _cancel_requested(cancelled)
        if is_cancelled:
            outcomes[node_id] = GraphNodeResult(
                node_id,
                InvocationStatus.CANCELLED,
                failure=FailureDetail(
                    category=FailureCategory.CANCELLED,
                    code="CANCELLED",
                    message="graph execution was cancelled before this node",
                    refs=(node_id,),
                ),
            )
            continue
        if max_duration_ms is not None and (time.monotonic() - started) * 1000 >= max_duration_ms:
            outcomes[node_id] = GraphNodeResult(
                node_id,
                InvocationStatus.TIMED_OUT,
                failure=FailureDetail(
                    category=FailureCategory.TIMEOUT,
                    code="GRAPH_TIMEOUT",
                    message="graph duration budget was exhausted before this node",
                    refs=(node_id,),
                ),
            )
            continue
        if max_invocations is not None and invocation_count >= max_invocations:
            outcomes[node_id] = GraphNodeResult(
                node_id,
                InvocationStatus.BLOCKED,
                failure=FailureDetail(
                    category=FailureCategory.BUDGET,
                    code="GRAPH_INVOCATION_BUDGET",
                    message="graph invocation budget was exhausted",
                    refs=(node_id,),
                ),
            )
            continue
        invocation_count += 1
        try:
            value = invoke(node)
        except Exception:
            outcomes[node_id] = GraphNodeResult(
                node_id,
                InvocationStatus.FAILED,
                failure=FailureDetail(
                    category=FailureCategory.PROVIDER,
                    code="NODE_EXECUTION_FAILED",
                    message="graph node execution failed",
                    refs=(node_id,),
                ),
            )
        else:
            if isinstance(value, GraphNodeResult):
                if value.node_id != node_id:
                    outcomes[node_id] = GraphNodeResult(
                        node_id,
                        InvocationStatus.FAILED,
                        failure=FailureDetail(
                            category=FailureCategory.PROVIDER,
                            code="NODE_RESULT_CORRELATION",
                            message="graph node result did not match the node identity",
                            refs=(node_id,),
                        ),
                    )
                else:
                    outcomes[node_id] = (
                        value
                        if value.failure is not None or value.status is InvocationStatus.SUCCEEDED
                        else GraphNodeResult(
                            value.node_id,
                            value.status,
                            value=value.value,
                            failure=_normalized_failure(value.node_id, value.status),
                            blocked_by=value.blocked_by,
                        )
                    )
            else:
                outcomes[node_id] = GraphNodeResult(
                    node_id, InvocationStatus.SUCCEEDED, value=value
                )
    return tuple(outcomes[node_id] for node_id in order)


validate_graph = validate_execution_graph
graph_order = topological_order
