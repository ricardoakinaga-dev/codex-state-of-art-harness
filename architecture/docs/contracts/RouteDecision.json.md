# RouteDecision — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `RD-1` · **Não executável**

`RouteDecision` explica por que uma capability foi selecionada, carregada ou deliberadamente omitida. O router não pode inventar disponibilidade: o registry e a fronteira nativa do host são fontes separadas. Ver [`06-routing-system.md`](../06-routing-system.md) e [`04-authority-model.md`](../04-authority-model.md).

```yaml
RouteDecision:
  schema_version: RD-1
  decision_id: ROUTE-0001
  task_id: TASK-0001
  run_id: RUN-0001
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [LOCAL, GENERATED, TOOL_OUTPUT]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  profile_ref: TASK-0001@TP-1
  route_status: [SELECTED, NO_SPECIAL_ROUTE, CONDITIONAL, FALLBACK, BLOCKED, REJECTED]
  route_kind: [DIRECT, SPECIALIST, COMPOSED, PROVIDER, DEGRADED]
  selected:
    - capability_id: string
      role: [DIRECTOR, ORCHESTRATOR, PLANNER, SPECIALIST, TOOL, PROVIDER, RESEARCHER, INTEGRATOR, VERIFICATION, REVIEWER, ASSURANCE, VALIDATOR, UTILITY]
      reason: string
      required: boolean
  optional:
    - capability_id: string
      when: string
      reason: string
  omitted:
    - capability_id: string
      reason_code: [OUT_OF_SCOPE, DUPLICATE, OVERACTIVATION, UNAVAILABLE, NOT_NEEDED, CONFLICT]
      explanation: string
  decision:
    precedence_rule_ids: [string]
    activation_reasons: [string]
    non_activation_reasons: [string]
    alternatives_considered: [string]
  compatibility:
    native_tools_considered: [string]
    provider_constraints: [string]
    conflicts_checked: [string]
  budget:
    token_estimate: integer|null
    latency_budget_ms: integer|null
    parallelism_budget: integer
  quality_gates: [string]
  context_budget:
    max_skill_kernels: integer|null
    max_reference_pack: [MINIMAL, STANDARD, EXTENDED]|null
  fallback: string|null
  confidence: [LOW, MEDIUM, HIGH]
  unresolved: [string]
  authority_ref: string
  created_at: timestamp
```

Invariantes: `selected` não pode conter `DIRECTOR` sem `task_profile` compatível; cada capability omitida precisa de razão; `NO_SPECIAL_ROUTE` é uma decisão válida, não ausência de decisão; `confidence: HIGH` exige evidência de manifest/host disponível; mudança no profile ou registry invalida a decisão.
