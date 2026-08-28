# 12 — Composition Contracts

## Propósito

Composição é uma relação explícita entre capabilities, não uma sequência implícita de prompts. O contrato evita que duas peças possuam a mesma decisão, que um provider vire director ou que assurance seja carregado sem verification.

## Campos

Cada capability declara:

```yaml
composition:
  can_call: []
  can_be_called_by: []
  must_run_before: []
  must_run_after: []
  conflicts_with: []
  optional_with: []
  do_not_combine_with: []
```

Cada um dos 12 records em `docs/contracts/` também possui um envelope comum, mesmo quando o tipo adiciona um lifecycle mais específico:

```yaml
record:
  status: [DRAFT, CURRENT, STALE, SUPERSEDED, INVALID, BLOCKED]
  provenance:
    source_type: [LOCAL, OFFICIAL, THIRD_PARTY, USER_PROVIDED, GENERATED, TOOL_OUTPUT, HUMAN]
    source_refs: [string]
    created_at: timestamp
  evidence_refs: [EVID-*]
```

`schema_version` e o ID primário do tipo ficam no nível superior. `record.status` descreve validade do record; `route_status`, `graph_status`, `artifact_status`, `result`, `verification` e `task_status` descrevem o domínio. `record.provenance` não substitui a proveniência detalhada do tipo, e `evidence_refs: []` é permitido somente quando a criação ainda não exige evidence e isso é declarado em `limitations`/`unknown`.

As relações são direcionais quando há dependência. `optional_with` não cria obrigação. `conflicts_with` exige resolução/owner, não significa que os packages sejam apagados.

## Contratos canônicos

| Producer | Consumer | Input contract | Output contract | Prohibited shortcut |
| --- | --- | --- | --- | --- |
| Director | Orchestrator | graph, owners, dependencies, budget, acceptance | task results/statuses | orchestrator não redefine goal |
| Director | Specialist | scoped handoff, domain boundary, quality criteria | domain artifact + evidence | specialist não amplia scope |
| Specialist | Tool/Provider | invocation with limits, auth and expected observation | raw result/provenance | não inventar tool result |
| Orchestrator | Integrator | completed/partial lane artifacts, conflicts | integrated candidate | não descartar partial failure |
| Integrator | Verification | candidate, acceptance, regression surface | verification report | não chamar artifact verified |
| Verification | Reviewer | claims, evidence, limitations, bar | critique report | reviewer não herda verdict como fato |
| Reviewer | Assurance | findings, severity, confidence, missing evidence | quality/stop decision | assurance não reescreve bar |
| Researcher | Integrator | sourced facts, freshness, source quality | cited synthesis | provider não é síntese automática |
| Design Director | Frontend | visual brief, tokens, states, viewport matrix | rendered implementation/evidence | design não owns backend |
| Verification | Gauntlet | current report + frozen bar + artifacts | adversarial gap/stop | gauntlet não substitui procedure |

## Exemplos solicitados

### Engineering Director → Orchestrator

`engineering-director` cria `ExecutionGraph`; `orchestrator` somente executa se DAG possui lanes independentes. O graph é a autoridade da execução, enquanto acceptance continua com Director/verification.

### Verification → Gauntlet

`verification` fornece claims, procedures, results, limitations e confidence. `gauntlet` não assume que um `PASS` de verification é qualidade final: compara contra bar, desafia gaps e decide stop/repair.

### Frontend ↔ Design Director

Design Director owns thesis, hierarchy, tokens, visual states e acceptance visual. Frontend specialist owns code/interaction. Ambos compartilham visual brief e render ledger; nenhum pode afirmar fidelidade sem screenshot/runtime evidence.

### Research Director → Provider

Research Director escolhe o objetivo e source rubric. Um provider (native web, Exa, Context7 etc.) executa busca/fetch. Síntese só ocorre se requerida; providers não competem em paralelo sem uma hipótese comparativa.

### Game Director → game specialists

Game Director owns player outcome, art bible e quality profile. Gameplay, art, audio, physics e playtest possuem boundaries; asset pipeline não pode declarar fun-factor e playtest não reescreve architecture sem escalonamento.

## Conflitos

Resolver pela seguinte ordem local: owner do boundary → Integrator para compatibilidade → Director para strategy/acceptance → Policy/authority para risk. Se o conflito for externo (user/system/developer/safety), sair do contrato interno e aplicar autoridade do Codex.

## Contrato de handoff

Todo handoff material inclui: `source_artifact_ids`, `input_digest` ou versão, objetivo, scope, non-goals, constraints, required gates, tools, expected output, known-bad condition, time/token budget, evidence needed, owner e next boundary. Sem isso, o consumer não deve inferir.

## Versionamento e invalidacão

Mudança de schema, scope, owner, dependency ou quality gate invalida consumers dependentes. O Registry marca relações stale; o próximo run revalida. Um link antigo não é evidência de compatibilidade atual.

## Anti-patterns de composição

- `engineering-framework + orchestrate` obrigatório em toda tarefa grande;
- `verification + gauntlet` gerando dois verdicts finais;
- `deep-research + Exa + native web + market-research` para um lookup único;
- `graphic-creation + imagegen + fal + video` quando apenas uma imagem é necessária;
- `content-engine` regenerando o texto que `crosspost` deveria apenas adaptar;
- dois specialists escrevendo a mesma boundary;
- reviewer recebendo a defesa do builder e chamando isso de independent.
