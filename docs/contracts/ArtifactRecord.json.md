# ArtifactRecord — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `AR-1` · **Não executável**

Este record preserva outputs, versões, dependências e proveniência sem confundir artifact com aprovação. Ver [`26-artifact-model.md`](../26-artifact-model.md).

```yaml
ArtifactRecord:
  schema_version: AR-1
  artifact_id: ART-0001
  task_id: TASK-0001
  run_id: RUN-0001
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [LOCAL, USER_PROVIDED, GENERATED, TOOL_OUTPUT, HUMAN]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  artifact_type: [PLAN, TASK_GRAPH, SOURCE_PATCH, BUILD, SCREENSHOT, TEST_REPORT, SECURITY_REPORT, VERIFICATION_REPORT, CRITIQUE_REPORT, QUALITY_SCORE, FINAL_DELIVERY]
  title: string
  producer:
    capability_id: string
    invocation_id: INV-*|null
  content:
    locator: string|null
    digest: string
    media_type: string
    size_bytes: integer|null
  source_refs: [TASK-*, NODE-*, ART-*, EVID-*]
  contract_refs: [string]
  dependencies: [string]
  artifact_status: [CREATED, INSPECTED, VALIDATED, REVIEWED, ACCEPTED, PARTIAL, BLOCKED, SUPERSEDED]
  evidence_refs: [EVID-*]
  limitations: [string]
  security:
    data_class: [PUBLIC, INTERNAL, CONFIDENTIAL, SENSITIVE]
    redaction: [NONE, APPLIED, REQUIRED]
    access_policy: string
  provenance:
    origin: [USER_PROVIDED, GENERATED, TOOL_OUTPUT, IMPORTED, DERIVED]
    tool_or_process: string|null
    parent_artifacts: [ART-*]
    created_at: timestamp
  supersedes: ART-*|null
```

Invariantes: `artifact_id`, digest, producer, status e provenance são obrigatórios; conteúdo alterado cria novo digest/record; `ACCEPTED` não pode remover limitations; `FINAL_DELIVERY` deve apontar para verification/quality apropriados; locator externo sem digest é referência fraca e não prova integridade.
