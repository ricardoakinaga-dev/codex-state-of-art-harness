# CapabilityInvocation — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `CI-1` · **Não executável**

Uma invocation é uma chamada autorizada e delimitada a uma capability. Handoff, permissões, orçamento e evidência necessária são explícitos; o consumer não deve inferir escopo. Ver [`12-composition-contracts.md`](../12-composition-contracts.md), [`17-tool-selection.md`](../17-tool-selection.md) e [`23-security-model.md`](../23-security-model.md).

```yaml
CapabilityInvocation:
  schema_version: CI-1
  invocation_id: INV-0001
  task_id: TASK-0001
  run_id: RUN-0001
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [LOCAL, GENERATED, TOOL_OUTPUT]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  graph_node_id: NODE-0001|null
  caller:
    capability_id: string
    authority_ref: string
  callee:
    capability_id: string
    manifest_version: string
  objective: string
  scope: [string]
  non_goals: [string]
  inputs:
    artifact_refs: [ART-*]
    evidence_refs: [EVID-*]
    payload_digest: string
  handoff:
    acceptance_refs: [string]
    required_output_contracts: [string]
    known_bad_conditions: [string]
  limits:
    token_budget: integer|null
    duration_budget_ms: integer|null
    tool_call_budget: integer|null
    retry_budget: integer
  permissions: [string]
  requested_tools: [string]
  expected_evidence: [string]
  invocation_status: [REQUESTED, AUTHORIZED, RUNNING, SUCCEEDED, PARTIAL, FAILED, BLOCKED, CANCELLED]
  failure_refs: [string]
  started_at: timestamp|null
  completed_at: timestamp|null
```

Invariantes: caller não pode conceder autoridade externa; `AUTHORIZED` exige scope, permissions e budget; payload bruto pode ser omitido do log, mas seu digest deve permanecer; retry cria nova invocation ou versão correlacionada; `SUCCEEDED` requer output e evidence compatíveis, não apenas ausência de exceção.
