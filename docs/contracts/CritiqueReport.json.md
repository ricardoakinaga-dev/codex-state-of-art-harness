# CritiqueReport — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `CR-1` · **Não executável**

Critique é uma leitura adversarial de artifacts e verification contra um bar congelado. O reviewer não reexecuta autoridade externa nem transforma opinião em fato. Ver [`14-assurance-system.md`](../14-assurance-system.md) e [`22-aaa-definition.md`](../22-aaa-definition.md).

```yaml
CritiqueReport:
  schema_version: CR-1
  report_id: CRIT-0001
  task_id: TASK-0001
  run_id: RUN-0001
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [LOCAL, GENERATED, HUMAN]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  reviewed_artifacts: [ART-*]
  reviewed_reports: [VER-*, QUAL-*]
  quality_bar_ref: string
  independence: [BUILDER, SEPARATED_SELF, INDEPENDENT]
  findings:
    - finding_id: FIND-0001
      severity: [CRITICAL, HIGH, MEDIUM, LOW, NOTE]
      category: [CORRECTNESS, SECURITY, COMPLETENESS, USABILITY, PERFORMANCE, PROVENANCE, PROCESS]
      statement: string
      evidence_refs: [EVID-*]
      affected_refs: [ART-*, CLAIM-*]
      confidence: [LOW, MEDIUM, HIGH]
      disposition: [OPEN, ACCEPTED_RISK, FIXED, REJECTED_WITH_REASON]
      owner: string|null
  strengths: [string]
  missing_evidence: [string]
  stop_recommendation: [CONTINUE, REPAIR, STOP, ESCALATE]
  residual_risk: [NONE, LOW, MEDIUM, HIGH, UNKNOWN]
  limitations: [string]
  reviewer:
    capability_id: string
    blind_packet_digest: string|null
  created_at: timestamp
```

Invariantes: cada finding material tem evidence ou é explicitamente `UNKNOWN`; `CRITICAL`/`HIGH` aberto impede AAA salvo override autorizado e registrado; `INDEPENDENT` requer packet cego e processo separado; critique não substitui verification nem altera seus claims.
