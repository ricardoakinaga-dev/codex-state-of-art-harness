# 06 — Routing System

## Responsabilidade

O router converte `TaskProfile` em uma rota mínima, justificável e verificável. Ele não executa capabilities, não altera instruções do Codex e não chama tudo que compartilha palavras com o pedido. A decisão é um artefato versionado; o output deve explicar inclusões e exclusões.

## Precedência de routing

1. system/developer/user constraints, safety e permissões do host;
2. explicit user invocation e provider-specific invocation, validada contra scope e segurança;
3. risk/security/data/irreversibility escalation;
4. no-skill/direct route para trivial;
5. domain match exato e deliverable;
6. complexity/visual/research/parallelism overlays;
7. quality gates e assurance mínimos;
8. custo/contexto e preferências de provider dentro das regras anteriores.

Uma invocação explícita significa “considere esta capability”; não significa “bypass safety, scope, verification ou authority”. Se o usuário pede algo incompatível, o router retorna `BLOCKED`/`CONDITIONAL` e preserva a intenção original.

## Algoritmo conceitual

```text
receive goal
  → parse deliverable, constraints, domain and boundary
  → classify complexity/risk/visual/research/data/security
  → resolve explicit capability/provider requests
  → apply mandatory safety and authority gates
  → select smallest domain capability set
  → add optional overlays only with reason and benefit
  → compute do_not_activate set and budget
  → emit RouteDecision + evidence + unknowns
```

## RouteDecision

`route_status` é o estado da decisão: `SELECTED`, `NO_SPECIAL_ROUTE`, `CONDITIONAL`, `FALLBACK`, `BLOCKED` ou `REJECTED`. `route_kind` descreve a forma (`DIRECT`, `SPECIALIST`, `COMPOSED`, `PROVIDER`, `DEGRADED`). `UNAVAILABLE` não é um route status: é `omitted.reason_code` ou uma limitation de dependency. Se houver fallback seguro, use `FALLBACK`; sem fallback, use `BLOCKED`.

```yaml
RouteDecision:
  schema_version: RD-1
  decision_id: ROUTE-0001
  task_id: TASK-2026-0001
  run_id: RUN-2026-0001
  record:
    status: CURRENT
    provenance:
      source_type: GENERATED
      source_refs: [EVID-CLASSIFICATION-0001, EVID-REGISTRY-0001]
      created_at: timestamp
    evidence_refs: [EVID-CLASSIFICATION-0001, EVID-REGISTRY-0001]
  profile_ref: TASK-2026-0001@TP-1
  route_status: SELECTED # SELECTED | NO_SPECIAL_ROUTE | CONDITIONAL | FALLBACK | BLOCKED | REJECTED
  route_kind: SPECIALIST # DIRECT | SPECIALIST | COMPOSED | PROVIDER | DEGRADED
  selected:
    - capability_id: api-design
      role: SPECIALIST
      reason: request/response and pagination contract are in scope
      required: true
    - capability_id: verification
      role: VERIFICATION
      reason: public endpoint evidence is required
      required: true
  optional:
    - capability_id: documentation-lookup
      when: framework/API behavior is current or uncertain
      reason: freshness or ambiguity may require official docs
  omitted:
    - capability_id: graphic-creation
      reason_code: OUT_OF_SCOPE
      explanation: no visual deliverable
    - capability_id: orchestrate
      reason_code: OVERACTIVATION
      explanation: no independent lane or measurable delegation gain
  decision:
    precedence_rule_ids: [SAFETY-FIRST, MINIMUM-ROUTE]
    activation_reasons: [public-api-contract, verification-required]
    non_activation_reasons: [no-independent-lane, no-visual-deliverable]
    alternatives_considered: [direct-with-focused-check, composed-api-route]
  compatibility:
    native_tools_considered: [shell, test-runner]
    provider_constraints: []
    conflicts_checked: [engineering-framework, orchestrate, graphic-creation]
  budget:
    token_estimate: null
    latency_budget_ms: null
    parallelism_budget: 1
  quality_gates: [validation, authorization, integration-regression]
  context_budget:
    max_skill_kernels: 3
    max_reference_pack: MINIMAL
  fallback: direct-with-verification
  confidence: HIGH
  unresolved: []
  authority_ref: AUTH-ROUTE-0001
  created_at: timestamp
```

## Regras anti-overactivation

- Comece pela menor rota que cobre o deliverable; cada capability adicional precisa de `reason`, owner, expected output e gate.
- Nunca ative dois owners para a mesma decisão. `engineering-framework` define strategy/requirements; `orchestrate` executa graph; `verification` prova execução; `gauntlet` desafia qualidade.
- `orchestrate` exige pelo menos duas lanes independentes, isolamento de ownership, dependências explicitadas e benefício esperado.
- `gauntlet` exige high-risk/high-fidelity, pedido explícito de revisão pesada ou bar que não pode ser satisfeita por focused verification.
- `tdd-workflow`, `e2e-testing`, `security-review`, research synthesis e media providers são overlays condicionais; o trigger lexical isolado não basta.
- Um provider e um synthesis layer não competem por default: escolher provider primeiro; adicionar síntese só se o output exige comparação/decisão.
- Uma ferramenta nativa do Codex é preferida quando cobre a boundary com segurança e evidência equivalente; Skill adiciona workflow/policy, não duplicação mecânica.
- Limite de contexto/latência deve ser aplicado antes da expansão; se a rota não cabe, degrade de forma explícita.

## Fallbacks

| Situação | Fallback | O que permanece desconhecido |
| --- | --- | --- |
| domain claro, capability ausente | `FALLBACK` para rota direta + checklist mínimo; `omitted.reason_code=UNAVAILABLE` | cobertura especializada |
| router indisponível | Director/agent principal classifica com profile explícito | precisão causal do routing |
| capability opcional falha | continue lanes não dependentes; mantenha route `FALLBACK` e marque execução/artifact lifecycle `PARTIAL` | output dependente da capability |
| provider específico indisponível | provider nativo/alternativo permitido pela policy (`FALLBACK`) ou `BLOCKED` com `reason_code=UNAVAILABLE` | equivalência de qualidade/freshness |
| subagents indisponíveis | single-agent serial, separated self-review | independência física |
| classificação ambígua | `INSPECT`/research/clarification; não executar material | scale/risk final |
| no-skill candidate | direct path + verification proporcional | benefício que uma Skill poderia ter trazido |

## Ambiguous routing

Quando dois domains são plausíveis, o router deve:

1. listar top routes e sinal conflitante;
2. escolher a rota que preserva segurança e reversibilidade;
3. evitar ativar ambos se uma boundary ainda não está comprovada;
4. pedir clarificação somente se a escolha mudar produto, risco, custo material ou permissão;
5. registrar a alternativa descartada e trigger de reclassificação.

## No-skill route

`NO_SPECIAL_ROUTE` com `route_kind: DIRECT` é uma decisão válida: classificador encontrou scope local, não há gate de domínio material, e o custo de capability excede seu benefício. O relatório deve registrar `activate=[]`, `do_not_activate=[...]`, focused check e limitation “não houve specialist review”.

## Provider-specific invocation

Provider explícito pode mudar a escolha de ferramenta (`Exa`, `Context7`, `fal.ai`, ElevenLabs etc.), mas não assume synthesis ou implementação. Se a ferramenta não está disponível, o router deve produzir `BLOCKED` com `omitted.reason_code=UNAVAILABLE` ou usar `FALLBACK` autorizado e comparar evidência/freshness.

## Re-evaluation

Recalcular rota quando o profile, tool availability, scope, failure, evidence, budget ou acceptance mudar. Route decisions antigas permanecem no trace; a nova decision aponta `supersedes`.
