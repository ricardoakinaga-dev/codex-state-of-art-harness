# VerificationReport — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `VR-1` · **Não executável**

Verification responde o que foi alegado, testado, observado, falhou ou permaneceu desconhecido. Não é autorização de release nem review independente. Ver [`13-verification-system.md`](../13-verification-system.md).

```yaml
VerificationReport:
  schema_version: VR-1
  report_id: VER-0001
  task_id: TASK-0001
  run_id: RUN-0001
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [LOCAL, GENERATED, TOOL_OUTPUT, HUMAN]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  artifact_refs: [ART-*]
  acceptance_refs: [string]
  claims:
    - claim_id: CLAIM-0001
      text: string
      required: boolean
      status: [PASS, FAIL, PARTIAL, NOT_RUN, BLOCKED, UNKNOWN]
      evidence_refs: [EVID-*]
      limitation_refs: [string]
  procedures:
    - procedure_id: PROC-0001
      description: string
      status: [EXECUTED, FAILED_TO_RUN, BLOCKED, SKIPPED]
      result: [PASS, FAIL, PARTIAL, NOT_RUN]
      evidence_refs: [EVID-*]
  passed: [CLAIM-*]
  failed: [CLAIM-*]
  not_run: [string]
  unknown: [string]
  limitations: [string]
  coverage:
    required_claims: integer
    evidenced_claims: integer
    percentage: number|null
  confidence: [LOW, MEDIUM, HIGH]
  blockers: [string]
  recommendation: [PASS, PARTIAL, BLOCK, FAIL]
  verifier:
    capability_id: string
    independence: [BUILDER, SEPARATED_SELF, INDEPENDENT]
  created_at: timestamp
```

Invariantes: todo claim requerido termina em uma lista; `PASS` exige evidence válida e gate executado; `recommendation: PASS` não pode coexistir com required claim `FAIL`/`BLOCKED`; ausência de cobertura aparece em `not_run`/`unknown`; o report só é atual quando suas dependências estão frescas.
