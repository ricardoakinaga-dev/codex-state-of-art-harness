# EvidenceRecord — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `ER-1` · **Não executável**

Evidence é uma observação reproduzível ligada a um claim. Explanations, previsões e nomes de capabilities não satisfazem evidence. Ver [`13-verification-system.md`](../13-verification-system.md), [`18-telemetry.md`](../18-telemetry.md) e [`22-aaa-definition.md`](../22-aaa-definition.md).

```yaml
EvidenceRecord:
  schema_version: ER-1
  evidence_id: EVID-0001
  task_id: TASK-0001
  run_id: RUN-0001
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [LOCAL, OFFICIAL, THIRD_PARTY, USER_PROVIDED, TOOL_OUTPUT, HUMAN]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  claim_ref: CLAIM-0001
  evidence_kind: [OBSERVATION, TEST_RESULT, BUILD_RESULT, SCREENSHOT, TRACE, METRIC, STATIC_INSPECTION, SOURCE_CITATION, HUMAN_INSPECTION]
  procedure:
    procedure_id: PROC-0001
    description: string
    command_or_method: string
    executed: boolean
  result: [PASS, FAIL, PARTIAL, NOT_RUN, BLOCKED, UNKNOWN]
  observation: string
  artifact_refs: [ART-*]
  environment:
    host: string|null
    version: string|null
    fixture: string|null
    tool: string|null
  observed_at: timestamp
  freshness:
    status: [FRESH, STALE, UNKNOWN]
    invalidated_by: [string]
  provenance:
    source_type: [LOCAL, OFFICIAL, TOOL, HUMAN, PROVIDER, USER_PROVIDED]
    source_ref: string
    content_digest: string|null
  limitations: [string]
  confidence: [LOW, MEDIUM, HIGH]
  privacy_class: [PUBLIC, INTERNAL, CONFIDENTIAL, SENSITIVE]
```

Invariantes: `executed: false` nunca pode resultar em `PASS`; `result: PASS` exige observation concreta e procedure executada; evidence stale não satisfaz gate atual; toda evidence externa precisa de source ref e freshness; confidence não substitui qualidade do método.
