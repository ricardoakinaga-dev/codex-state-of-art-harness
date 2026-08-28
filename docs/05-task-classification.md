# 05 — Task Classification

## Objetivo

Classificação decide profundidade, não “importância” moral da tarefa. O classificador produz um perfil multidimensional; não reduz tudo a uma nota. Se um eixo material é `UNKNOWN`, o sistema deve fazer inspeção segura e evitar atividade material até resolver o desconhecido ou obter autoridade aplicável.

## Eixos

| Eixo | Pergunta | Valores de referência |
| --- | --- | --- |
| `DOMAIN` | qual fronteira principal será alterada? | `ENGINEERING`, `FRONTEND`, `BACKEND`, `API`, `SECURITY`, `DESIGN`, `RESEARCH`, `GAME`, `DATA`, `INFRASTRUCTURE`, `DOCUMENTATION`, `CONTENT`, `INTEGRATION`, `OPERATIONS`, `GENERAL`, `MIXED` |
| `COMPLEXITY` | quantos comportamentos, componentes e decisões? | `TRIVIAL`, `SMALL`, `MEDIUM`, `LARGE`, `CRITICAL` |
| `RISK` | qual o dano plausível de falha? | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, `UNKNOWN` |
| `VISUAL_IMPORTANCE` | pixels, interação ou fidelidade visual são parte do outcome? | `NONE`, `SUPPORTING`, `MATERIAL`, `PRIMARY` |
| `SECURITY_IMPACT` | cruza auth, secrets, input, privilege, network ou abuse? | `NONE`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `DATA_IMPACT` | lê, escreve, migra, apaga ou expõe dados? | `NONE`, `LOCAL`, `PERSISTENT`, `MIGRATION`, `SENSITIVE` |
| `USER_IMPACT` | quantas pessoas/fluxos e qual criticidade? | `INTERNAL`, `LIMITED`, `BROAD`, `SAFETY_RELEVANT` |
| `BLAST_RADIUS` | qual superfície pode ser afetada por uma falha? | `LOCAL`, `MODULE`, `SERVICE`, `PRODUCT`, `CROSS_SYSTEM`, `PUBLIC`, `UNKNOWN` |
| `RESEARCH_NEED` | fatos atuais/nicho/ambíguos precisam ser buscados? | `NONE`, `FRESHNESS_REQUIRED`, `COMPARATIVE`, `DEEP` |
| `PARALLELISM_POTENTIAL` | há lanes independentes com resultado verificável? | `NONE`, `LOW`, `MEDIUM`, `HIGH` |
| `REVERSIBILITY` | é fácil desfazer sem perda? | `EASY`, `CONTROLLED`, `HARD`, `IRREVERSIBLE` |
| `CONFIDENCE` | quão forte é a evidência do profile? | `LOW`, `MEDIUM`, `HIGH`, `UNKNOWN` |

Os tokens entre crases são os enums canônicos e devem aparecer sem lowercase no `TaskProfile`. Termos narrativos são mapeados antes de emitir o contrato: “high-fidelity” → `VISUAL_IMPORTANCE=PRIMARY`; “current” → `RESEARCH_NEED=FRESHNESS_REQUIRED`; “possible” → `PARALLELISM_POTENTIAL=MEDIUM/HIGH` somente com independência/benefício; “system” → `BLAST_RADIUS=CROSS_SYSTEM`. O contrato conceitual em [`contracts/TaskProfile.json.md`](./contracts/TaskProfile.json.md) deve permanecer idêntico a esta tabela.

## Regras de escalada

- `RISK=CRITICAL`, `REVERSIBILITY=IRREVERSIBLE`, `SECURITY_IMPACT=CRITICAL`, `DATA_IMPACT=MIGRATION/SENSITIVE` ou `BLAST_RADIUS=CROSS_SYSTEM` elevam para `CRITICAL` até evidência reduzir a classificação.
- `RISK=HIGH` ou `BLAST_RADIUS=CROSS_SYSTEM` exige ao menos rota `LARGE` com assurance proporcional.
- `VISUAL_IMPORTANCE=PRIMARY` exige render/inspection/critic, mesmo que o código alterado seja pequeno.
- `RESEARCH_NEED=FRESHNESS_REQUIRED` exige fonte atual; provider não é escolhido por tamanho do trabalho.
- `PARALLELISM_POTENTIAL=MEDIUM/HIGH` não justifica orchestration: é necessário ganho comprovado ou lanes que possam ser julgadas independentemente.
- `CONFIDENCE=LOW/UNKNOWN` adiciona discovery/inspection; não concede permissão para agir fora do scope.
- O maior risco prevalece sobre a média dos eixos; não se pode “compensar” critical por complexity small.

## Classes operacionais

| Classe | Critérios mínimos | Rota default | Gates e evidência | Exemplo |
| --- | --- | --- | --- | --- |
| `TRIVIAL` | uma alteração local/reversível; sem contrato, data, security ou visual material | direct/no-skill | diff + focused check; sem Director/Orchestrator/Gauntlet | corrigir typo |
| `SMALL` | uma função/componente/módulo; risco `LOW/MEDIUM`; boundary local | specialist opcional + verification focal | teste/check local + regressão próxima | corrigir bug CSS isolado |
| `MEDIUM` | vários passos ou uma fronteira service/API/data; risco até high controlado | Director opcional; specialists selecionados; verification | public boundary, errors, relevant security/data, regression | adicionar endpoint paginado |
| `LARGE` | múltiplos boundaries/milestones, arquitetura, pesquisa ou alto custo de falha | Director + plan/graph; Orchestrator só com gate; verification + review + assurance | integration, risk-shaped tests, evidence ledger, stop/recovery | landing premium + backend, refactor auth amplo |
| `CRITICAL` | risco `CRITICAL`, irreversibilidade, dados sensíveis, produção, financeiro/regulatório ou authority material | human boundary + Director + strongest review; execution constrained | failure-first, containment, recovery, explicit authority, re-audit | migração destrutiva, mudança de auth em produção |

## Profiles de complexidade

`COMPLEXITY` mede trabalho; `RISK` mede consequência. Uma tarefa pode ser `SMALL + CRITICAL` e deve seguir o floor crítico.

- **TRIVIAL:** uma intenção, uma superfície, um check.
- **SMALL:** uma responsabilidade e uma integração local.
- **MEDIUM:** duas ou mais responsabilidades relacionadas ou uma boundary pública.
- **LARGE:** graph com dependências, várias boundaries ou trabalho que sobrevive à sessão.
- **CRITICAL:** qualquer combinação cuja falha pode produzir dano severo/irreversível; não exige muitos arquivos.

## Profile mínimo emitido

```yaml
TaskProfile:
  schema_version: TP-1
  task_id: TASK-2026-0001
  run_id: RUN-2026-0001
  record:
    status: CURRENT
    provenance:
      source_type: LOCAL
      source_refs: [EVID-REPOSITORY-INSPECTION-001]
      created_at: timestamp
    evidence_refs: [EVID-REPOSITORY-INSPECTION-001]
  objective: add a paginated users endpoint
  requested_outcome: API endpoint, tests and verification report
  domain: BACKEND
  complexity: MEDIUM
  risk: MEDIUM
  visual_importance: NONE
  security_impact: MEDIUM
  data_impact: PERSISTENT
  user_impact: BROAD
  blast_radius: SERVICE
  research_need: FRESHNESS_REQUIRED
  parallelism_potential: NONE
  reversibility: CONTROLLED
  confidence: HIGH
  constraints: [preserve existing authorization contract]
  non_goals: [change unrelated user lifecycle]
  repository_context:
    root: /workspace/project
    classification: BROWNFIELD
    trust_state: TRUSTED
  evidence:
    refs: [EVID-REPOSITORY-INSPECTION-001]
    confidence: HIGH
  classification_trace:
    rule_ids: [PUBLIC-API, PERSISTENT-DATA, AUTH-BOUNDARY]
    assumptions: [endpoint remains idempotent for reads]
    unresolved: []
  created_at: timestamp
```

## Exemplos de classificação

| Pedido | Profile resumido | Classe | Observação |
| --- | --- | --- | --- |
| “corrigir typo” | local, low, none, reversible | TRIVIAL | não carregar processo |
| “adicionar endpoint” | API/service, persistent, boundary security | MEDIUM | API + backend + verification |
| “refatorar auth” | security high, cross-module, hard-to-reverse | LARGE/CRITICAL | review security obrigatório |
| “criar landing premium” | visual high, product/public, research verify | LARGE | Director visual + frontend + render/critic |
| “pesquisar API atual” | research current, read-only, reversible | SMALL/MEDIUM | fonte atual e citation |
| “migrar banco” | data migration, persistent/irreversible | CRITICAL | human authority/recovery |

## Reclassificação

Reclassificar quando surgirem novo data flow, auth boundary, provider, user impact, dependency, unknown material ou mudança de deliverable. A mudança invalida route/gates dependentes; não se deve preservar um status de “small” para manter velocidade.

## Evidência da classificação

Cada dimensão material precisa de observação, documento, comando, user constraint ou explicit `UNKNOWN`. Números de risco sem método são pseudoprecisão. O classificador deve guardar alternativas consideradas e reason de escalada, permitindo que um reviewer detecte underclassification.
