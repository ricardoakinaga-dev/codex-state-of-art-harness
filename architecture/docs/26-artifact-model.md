# 26 — Artifact Model

## Artefatos canônicos

| Type | Produzido por | Uso | Não prova sozinho |
| --- | --- | --- | --- |
| `PLAN` | Director/Planner | strategy, scope, acceptance | implementation |
| `TASK_GRAPH` | Planner/Orchestrator | dependency/ownership | quality |
| `SOURCE_PATCH` | Specialist/Builder | changed source | runtime correctness |
| `BUILD` | Tool/CI | compiled/package output | UX/security |
| `SCREENSHOT` | Browser/visual tool | rendered visual evidence | all responsive states |
| `TEST_REPORT` | Verification | procedure/result | product quality global |
| `SECURITY_REPORT` | Security Review | threat/findings | no vulnerability universe |
| `VERIFICATION_REPORT` | Verification | claims/evidence/limits | independent critique |
| `CRITIQUE_REPORT` | Reviewer | gaps/severity/confidence | root cause automatically |
| `QUALITY_SCORE` | Assurance/rubric | anchored prioritization | required gate override |
| `FINAL_DELIVERY` | Integrator/authorized owner | packaged output | unrun claims |

## Record comum

```yaml
artifact_record:
  artifact_id: ART-0001
  type: VERIFICATION_REPORT
  producer: verification
  created_at: 2026-08-28T12:00:00Z
  source: [TASK-1, ART-0000]
  status: CURRENT
  confidence: HIGH
  dependencies: [CONTRACT-VERIFICATION-V1]
  provenance:
    origin: generated-from-run
    tool_or_process: verification-runner
    input_digest: sha256:...
  evidence_refs: [EVID-1]
  limitations: ["isolated environment"]
```

## Lifecycle

`CREATED → INSPECTED → VALIDATED → REVIEWED → ACCEPTED | PARTIAL | BLOCKED | SUPERSEDED`. Status de artifact não é status de gate. `SUPERSEDED` preserva predecessor e reason.

## Identity e provenance

Artifact ID é único no run/registry; content digest identifica bytes/conteúdo; source refs ligam requisito/task/tool. Não sobrescrever artifact aceito sem nova versão. Paths/URLs sem digest são referência fraca.

## Retenção e segurança

Raw logs/screenshots podem conter secrets/PII; redaction/access/retention são parte do artifact policy. Um artifact incompleto deve ser preservado se necessário para diagnóstico, mas marcado claramente.

## Integração

Integrator deve verificar producer, version, dependencies, status, evidence e scope antes de usar artifact. Um artifact “PASS” de um lane não satisfaz um gate global sem coverage.
