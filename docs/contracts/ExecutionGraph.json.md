# ExecutionGraph — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `EG-1` · **Não executável**

O graph representa trabalho autorizado, dependências e ownership. Ele não transforma uma lista de agentes em paralelismo: a DAG precisa demonstrar independência, merge e gates. Ver [`07-orchestration-model.md`](../07-orchestration-model.md).

```yaml
ExecutionGraph:
  schema_version: EG-1
  graph_id: GRAPH-0001
  task_id: TASK-0001
  run_id: RUN-0001
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [LOCAL, GENERATED, HUMAN]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  goal: string
  nodes:
    - node_id: NODE-0001
      kind: [DIRECTOR, PLANNER, SPECIALIST, TOOL, INTEGRATOR, VERIFICATION, REVIEWER, ASSURANCE]
      capability_id: string
      owner: string
      input_refs: [ART-*, EVID-*, NODE-*]
      output_contract: string
      depends_on: [NODE-*]
      can_parallelize: boolean
      required: boolean
      budget:
        tokens: integer|null
        duration_ms: integer|null
      acceptance_refs: [string]
  edges:
    - from: NODE-0001
      to: NODE-0002
      relation: [DATA, CONTROL, GATE]
  merge_points:
    - node_id: NODE-0003
      conflict_owner: [INTEGRATOR, DIRECTOR, AUTHORITY]
      unresolved_policy: [PRESERVE_AND_ESCALATE, BLOCK, DROP_WITH_REASON]
  graph_status: [DRAFT, READY, RUNNING, PARTIAL, BLOCKED, COMPLETED, CANCELLED]
  stop_policy_ref: string
  created_at: timestamp
```

Invariantes: IDs são únicos; edges não formam ciclo; nenhum node requerido fica sem owner, input contract ou output contract; `can_parallelize` só pode ser verdadeiro quando dependências e side effects permitirem; merge não apaga dissent; graph `COMPLETED` não implica qualidade aceita.
