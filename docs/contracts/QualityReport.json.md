# QualityReport — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `QR-1` · **Não executável**

Quality agrega dimensões e gates para apoiar decisão; não é média cega que possa ultrapassar um blocker. Ver [`21-quality-model.md`](../21-quality-model.md), [`22-aaa-definition.md`](../22-aaa-definition.md) e [`14-assurance-system.md`](../14-assurance-system.md).

```yaml
QualityReport:
  schema_version: QR-1
  report_id: QUAL-0001
  task_id: TASK-0001
  run_id: RUN-0001
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [LOCAL, GENERATED, HUMAN, TOOL_OUTPUT]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  profile: string
  artifact_refs: [ART-*]
  verification_ref: VER-*|null
  critique_ref: CRIT-*|null
  dimensions:
    - dimension: [CORRECTNESS, COMPLETENESS, USABILITY, PERFORMANCE, SECURITY, OPERABILITY, PROVENANCE, VISUAL_FIDELITY]
      score: number|null
      confidence: [LOW, MEDIUM, HIGH]
      evidence_refs: [EVID-*]
      limitations: [string]
  gates:
    - gate_id: string
      status: [PASS, FAIL, PARTIAL, NOT_RUN, BLOCKED]
      required: boolean
      evidence_refs: [EVID-*]
  quality_band: [AAA_VERIFIED, AAA_CANDIDATE, ACCEPTABLE, PARTIAL, BLOCKED, FAILED]
  open_findings: [FIND-*]
  residual_risk: [NONE, LOW, MEDIUM, HIGH, UNKNOWN]
  decision: [DELIVER, DELIVER_WITH_LIMITATIONS, REPAIR, STOP, ESCALATE]
  decision_owner: string
  created_at: timestamp
```

Invariantes: required gate `FAIL`/`BLOCKED` impede `AAA_VERIFIED`; score sem evidence é `null` ou confidence `LOW`; `decision_owner` é obrigatório; residual risk nunca desaparece por arredondamento; `DELIVER_WITH_LIMITATIONS` lista as limitações no mesmo report.
