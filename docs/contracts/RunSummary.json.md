# RunSummary — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `RS-1` · **Não executável**

`RunSummary` é a visão final de uma execução, reunindo rota, graph, artifacts, evidence, qualidade, custo e limitações. Ele não cola status incompatíveis em um único `PASS`: task, gates, verification e delivery continuam distinguíveis. Ver [`27-state-model.md`](../27-state-model.md) e [`22-aaa-definition.md`](../22-aaa-definition.md).

```yaml
RunSummary:
  schema_version: RS-1
  summary_id: SUMMARY-0001
  task_id: TASK-0001
  run_id: RUN-0001
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [LOCAL, GENERATED, TOOL_OUTPUT, HUMAN]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  lifecycle_state: [NEW, CLASSIFIED, ROUTED, PLANNED, EXECUTING, VERIFYING, REVIEWING, REPAIRING, ASSURING, PASSED, DELIVERED, PARTIAL, BLOCKED, FAILED, CANCELLED]
  route_ref: ROUTE-*
  profile_ref: TASK-*TP-1
  graph_ref: GRAPH-*|null
  selected_capabilities: [string]
  loaded_capabilities: [string]
  artifacts: [ART-*]
  evidence: [EVID-*]
  verification_ref: VER-*|null
  critique_ref: CRIT-*|null
  quality_ref: QUAL-*|null
  gate_summary:
    passed: [string]
    failed: [string]
    not_run: [string]
    blocked: [string]
  execution:
    started_at: timestamp
    completed_at: timestamp|null
    duration_ms: integer|null
    retries: integer
    stop_reason: string|null
  resource_usage:
    token_estimate: integer|null
    cost_estimate: number|null
    tool_calls: integer
    parallel_lanes: integer
  delivery:
    status: [NOT_DELIVERED, DELIVERED, DELIVERED_WITH_LIMITATIONS, BLOCKED]
    artifact_ref: ART-*|null
    decision_owner: string|null
  limitations: [string]
  open_questions: [string]
  confidence: [LOW, MEDIUM, HIGH]
  created_at: timestamp
```

Invariantes: todo ID referenciado existe e é da mesma execução; `DELIVERED` exige delivery artifact e required gates; `BLOCKED` ou `PARTIAL` não pode ser apresentado como AAA; `loaded_capabilities` só inclui load observado ou é marcado como unknown; summary é imutável por versão.
