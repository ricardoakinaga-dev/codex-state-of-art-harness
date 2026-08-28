# TaskProfile — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `TP-1` · **Não executável**

Este registro é a classificação normalizada de uma solicitação antes do routing. Ele separa o que foi observado do que foi inferido e não autoriza, por si só, a execução de nenhuma capability. Ver [`05-task-classification.md`](../05-task-classification.md) e [`contracts/`](../README.md).

```yaml
TaskProfile:
  schema_version: TP-1
  task_id: TASK-0001
  run_id: RUN-0001
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [USER_PROVIDED, LOCAL, GENERATED]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  objective: string
  requested_outcome: string
  domain: [ENGINEERING, FRONTEND, BACKEND, API, SECURITY, DESIGN, RESEARCH, GAME, DATA, INFRASTRUCTURE, DOCUMENTATION, CONTENT, INTEGRATION, OPERATIONS, GENERAL, MIXED]
  complexity: [TRIVIAL, SMALL, MEDIUM, LARGE, CRITICAL]
  risk: [LOW, MEDIUM, HIGH, CRITICAL, UNKNOWN]
  visual_importance: [NONE, SUPPORTING, MATERIAL, PRIMARY]
  security_impact: [NONE, LOW, MEDIUM, HIGH, CRITICAL]
  data_impact: [NONE, LOCAL, PERSISTENT, MIGRATION, SENSITIVE]
  user_impact: [INTERNAL, LIMITED, BROAD, SAFETY_RELEVANT]
  blast_radius: [LOCAL, MODULE, SERVICE, PRODUCT, CROSS_SYSTEM, PUBLIC, UNKNOWN]
  research_need: [NONE, FRESHNESS_REQUIRED, COMPARATIVE, DEEP]
  parallelism_potential: [NONE, LOW, MEDIUM, HIGH]
  reversibility: [EASY, CONTROLLED, HARD, IRREVERSIBLE]
  confidence: [LOW, MEDIUM, HIGH, UNKNOWN]
  constraints: [string]
  non_goals: [string]
  repository_context:
    root: string|null
    classification: [GREENFIELD, BROWNFIELD, UNKNOWN]
    trust_state: [TRUSTED, UNTRUSTED, UNKNOWN]
  evidence:
    refs: [EVID-*]
    confidence: [LOW, MEDIUM, HIGH, UNKNOWN]
  classification_trace:
    rule_ids: [string]
    assumptions: [string]
    unresolved: [string]
  created_at: timestamp
```

Invariantes: `objective`, `domain`, `complexity`, `risk` e `created_at` são obrigatórios; `CRITICAL` em qualquer eixo exige gate de segurança/autoridade correspondente; uma inferência sem `assumptions` é inválida; reclassificação cria nova versão e não edita o registro anterior.
