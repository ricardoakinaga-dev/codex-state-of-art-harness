# TelemetryEvent — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `TE-1` · **Não executável**

Telemetry é evidence operacional append-only, com privacy class e correlação. O evento `CAPABILITY_LOADED` só é causal quando o host realmente expõe observação de load; um self-report não basta. Ver [`18-telemetry.md`](../18-telemetry.md) e [`19-observability.md`](../19-observability.md).

```yaml
TelemetryEvent:
  schema_version: TE-1
  event_id: EVT-0001
  event_sequence: integer
  timestamp: timestamp
  task_id: TASK-0001
  run_id: RUN-0001
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [LOCAL, TOOL_OUTPUT, GENERATED]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  parent_event_id: EVT-*|null
  event_type: [TASK_RECEIVED, TASK_CLASSIFIED, ROUTE_SELECTED, CAPABILITY_SELECTED, CAPABILITY_LOADED, TOOL_CALLED, TOOL_RESULT, RETRY, VALIDATION_RUN, VALIDATION_FAIL, CRITIQUE_RUN, GAUNTLET_PASS, GAUNTLET_FAIL, DELIVERY]
  actor:
    capability_id: string|null
    invocation_id: INV-*|null
  reason: string|null
  payload:
    input_size: integer|null
    output_size: integer|null
    token_estimate: integer|null
    duration_ms: integer|null
    tool: string|null
    result: [PASS, FAIL, PARTIAL, BLOCKED, UNKNOWN, null]
  artifact_refs: [ART-*]
  evidence_refs: [EVID-*]
  privacy_class: [PUBLIC, INTERNAL, CONFIDENTIAL, SENSITIVE]
  redaction: [NONE, APPLIED, REQUIRED]
  integrity:
    previous_event_digest: string|null
    event_digest: string
    ordering: [IN_ORDER, OUT_OF_ORDER, UNKNOWN]
  limitations: [string]
```

Invariantes: `event_id`, sequence, timestamp, task/run correlation, event type e digest são obrigatórios; raw secrets/prompts/PII não entram no payload; perda ou reorder fica sinalizado; `DELIVERY` precisa de evidence de delivery, não apenas ausência de erro; métricas derivadas preservam baseline e sample.
