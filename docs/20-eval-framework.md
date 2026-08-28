# 20 — Eval Framework

## Objetivo

Evals medem se uma capability ou o Harness melhora comportamento em cenários fixos. Evals não substituem verification da mudança atual e não permitem declarar causalidade sem controle válido.

## Níveis

| Tipo | Unidade | Oracle | Exemplo |
| --- | --- | --- | --- |
| `UNIT EVAL` | regra/validator/transform | determinístico | manifest rejeita missing `do_not_activate` |
| `INTEGRATION EVAL` | duas ou mais capabilities/tools | contract + artifact | router → specialist → verification |
| `CAPABILITY EVAL` | uma capability em seu scope | rubric/known-bad | backend rejeita input inválido |
| `HARNESS EVAL` | route/lifecycle/authority/context | outcome + telemetry | no-skill vs routed path |
| `REGRESSION EVAL` | cenário já aprovado | versioned expected | S1–S5 após mudança |
| `HUMAN EVAL` | qualidade não determinística | blind rubric | specificity/UX/domain judgment |

## Suites permanentes

```text
evals/
├── routing/
├── backend/
├── frontend/
├── security/
├── design/
├── research/
├── games/
├── assurance/
├── composition/
└── context-efficiency/
```

Cada cenário define prompt, fixture, preconditions, expected, required/forbidden actions, expected artifacts, human stop, oracle e `known_bad`. Positive e negative routing são obrigatórios.

## Routing metrics

- precision: proporção de capabilities ativadas que eram mínimas/justificadas;
- recall: proporção de capabilities/gates mínimos necessários cobertos;
- overactivation count: ativação além da composição adjudicada;
- miss count: ausência de capability/gate requerido;
- route context cost: measured loaded tokens; word count é proxy;
- simple-task latency: no-skill regressions;
- quality delta: blind outcome score versus control.

N=5 do audit é baseline exploratório, não suite suficiente. A próxima comparação deve usar famílias fixas, ≥20 prompts por família quando viável, native-only/current/vNext controls, host-load trace e blind grading.

## Domain suites

- **Backend/API:** schema, validation, auth, status/errors, persistence, idempotence, timeout, integration.
- **Frontend/design:** real render, states, viewport, keyboard, accessibility, console/network, specificity.
- **Security:** trust boundaries, abuse, secret/input/path injection, authorization and auditability.
- **Research:** freshness, primary-source quality, citation accuracy, synthesis separation.
- **Games:** playable loop, input, readability, asset provenance, performance, playtest evidence.
- **Assurance/composition:** no self-approval, bounded retries, conflict resolution, DAG ownership.
- **Context:** quality retained under smaller reference packs, no duplicated context, cost/latency.

## Known-bad validation

Antes de confiar em um eval, demonstrar que uma implementação conhecida-bad falha. Exemplos: router que ativa todos os specialists deve falhar overactivation; verification sem procedure deve falhar PASS; gauntlet sem stop budget deve falhar assurance; contract sem `evidence_refs` deve falhar schema.

## Promotion

Uma capability só avança de candidate após evals atuais, regression sem critical regression, benchmark cost/quality, review independente proporcional e provenance. Evals podem recomendar rejeição/defer, não autoeditar Skill instalada.
