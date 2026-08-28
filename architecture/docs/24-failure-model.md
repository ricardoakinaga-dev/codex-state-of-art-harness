# 24 — Failure Model

## Catálogo

| Failure | Detection | Severity | Recovery | Escalation |
| --- | --- | --- | --- | --- |
| `ROUTING_FAILURE` | route missing/overactivated/contradictory | medium–high | reclassify, fallback direct, preserve route trace | Director/Policy |
| `TOOL_FAILURE` | nonzero/timeout/schema/permission | medium–high | bounded idempotent retry or fallback | Tool owner/Orchestrator |
| `DEPENDENCY_FAILURE` | required package/provider/contract absent | high | block dependents, run independent work | Director/user if outcome changes |
| `VALIDATION_FAILURE` | check fails or harness invalid | high | diagnose root cause, repair, rerun | Verification/Assurance |
| `CONTEXT_FAILURE` | overflow, stale summary, missing required context | medium–high | slice/refresh/replan | Context Manager/Director |
| `LOOP_FAILURE` | no progress, repeated failure, oscillation, budget | high | stop and replan; no blind retry | Assurance |
| `CRITIC_FAILURE` | critic unavailable/biased/incomplete | medium–high | stronger deterministic evidence or new critic | Assurance; limitation |
| `PROVIDER_FAILURE` | auth/rate/freshness/outage | medium | authorized fallback or partial | Router/Research Director |
| `SECURITY_BLOCK` | unsafe operation, permission, secret, abuse | critical | stop, contain, redact, request authority | Policy/human security owner |
| `USER_CONSTRAINT_CONFLICT` | requirement contradicts higher instruction/approved scope | high | preserve intent, explain conflict, ask smallest decision | User/authority |

## Failure record

```yaml
failure:
  failure_id: FAIL-01
  class: VALIDATION_FAILURE
  task_id: TASK-1
  observed: "link checker found unresolved target"
  evidence_refs: [EVID-9]
  impact: HIGH
  containment: "delivery blocked"
  recovery: "repair link and rerun checker"
  retries: 0
  escalation: assurance
  status: OPEN
```

## Failure versus partial success

Uma lane pode passar enquanto outra falha. Integrator conserva outputs independentes e marca dependents. Global delivery usa o status mais restritivo dos required criteria; não faz média.

## Root cause

Critic/validator aponta sintoma. Builder/Lead confirma root cause com evidence discriminating. Sugestão de fix do critic é hipótese. Após mudança, rerun focused procedure e regression surface.

## Recovery safety

Nunca repetir external side effect só porque log não tem success. Inspecionar estado autoritativo, idempotence e locks; se não houver autorização, bloquear. O recovery report preserva falha original e novo evento.
