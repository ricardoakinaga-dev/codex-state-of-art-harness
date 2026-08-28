# CapabilityManifest — contrato conceitual

**Status:** `PROPOSED` · **Versão:** `CM-1` · **Não executável**

O manifest é a identidade verificável de uma capability no Registry. `description` ajuda matching, mas o router precisa usar escopo, contrato, dependências, conflicts e evidence. Ver [`10-capability-package-standard.md`](../10-capability-package-standard.md) e [`11-skill-md-standard.md`](../11-skill-md-standard.md).

```yaml
CapabilityManifest:
  schema_version: CM-1
  capability_id: string
  display_name: string
  version: semver|string
  record:
    status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
    provenance:
      source_type: [LOCAL, OFFICIAL, THIRD_PARTY, GENERATED]
      source_refs: [string]
      created_at: timestamp
    evidence_refs: [EVID-*]
  primary_type: [DIRECTOR, ORCHESTRATOR, ROUTER, PLANNER, SPECIALIST, TOOL, PROVIDER, REVIEWER, VALIDATOR, ASSURANCE, RESEARCHER, INTEGRATOR, UTILITY]
  status: [CANDIDATE, EXPERIMENTAL, VERIFIED, ACTIVE, DEPRECATED, REJECTED]
  owner: string
  scope:
    domains: [string]
    activates_when: [string]
    do_not_activate_when: [string]
    minimum_task_class: [TRIVIAL, SMALL, MEDIUM, LARGE, CRITICAL]
  contracts:
    inputs: [string]
    outputs: [string]
    gates: [string]
    stop_conditions: [string]
  composition:
    can_call: [string]
    can_be_called_by: [string]
    must_run_before: [string]
    must_run_after: [string]
    conflicts_with: [string]
  dependencies:
    capabilities: [string]
    tools: [string]
    providers: [string]
    references: [string]
  provenance:
    source_type: [LOCAL, OFFICIAL, THIRD_PARTY, USER_PROVIDED, GENERATED]
    source_refs: [string]
    inspected_at: timestamp
  compatibility:
    host_features: [string]
    platform_limits: [string]
  quality:
    profile: string
    eval_refs: [string]
    benchmark_refs: [string]
    last_result: [PASS, PARTIAL, FAIL, NOT_RUN]
  security:
    permissions: [string]
    data_classes: [string]
    secret_policy: string
  context_cost:
    metadata_tokens_estimate: integer|null
    body_tokens_estimate: integer|null
  deprecation:
    successor: string|null
    reason: string|null
```

Invariantes: `capability_id`, `version`, `primary_type`, `status`, `owner`, `scope`, `contracts`, `provenance` e `security` são obrigatórios; capability sem source/eval não pode ser `VERIFIED`; conflicts não podem ser ocultados; `ACTIVE` requer gates e fallback declarados; manifest não afirma que um tool existe no host.
