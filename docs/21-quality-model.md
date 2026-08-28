# 21 — Quality Model

## Dimensões

| Dimensão | Pergunta | Evidência típica |
| --- | --- | --- |
| correctness | o resultado satisfaz behavior/contract? | public-boundary test, artifact inspection |
| reliability | funciona sob retry, timeout, partial failure e repetição? | failure tests, trace, repeated run |
| security | boundaries e abuse cases estão controlados? | threat matrix, security review, scan/test |
| maintainability | ownership, dependency e mudanças futuras são claros? | architecture/contract inspection |
| architecture | componentes têm reason-to-exist e direção? | ADR, graph, dependency check |
| UX | usuário consegue completar ação e recuperar erro? | runtime interaction, human eval |
| visual quality | hierarchy, type, spacing, states, specificity e fidelity? | native render/screenshots/critic |
| performance | latency/resource/cost estão adequados? | representative benchmark/tails |
| accessibility | semantics, keyboard, focus, contrast, reflow e motion? | automated + manual runtime |
| evidence | claims são atuais, reproduzíveis e completos? | verification ledger |
| efficiency | quality por contexto/token/latency é aceitável? | controlled comparison |

Nem toda dimensão aplica a toda tarefa. Inaplicável deve ter rationale; missing evidence não é `N/A`.

## Quality profiles

| Profile | Required dimensions | Typical gates |
| --- | --- | --- |
| `DIRECT_TRIVIAL` | correctness, evidence | focused check, diff |
| `API_SERVICE` | correctness, reliability, security, evidence, maintainability | boundary contract, validation/auth, integration/regression |
| `DATA_MIGRATION` | correctness, data integrity, security, recovery, evidence | isolated migration, rollback/roll-forward, authority |
| `FRONTEND_PRODUCT` | correctness, UX, accessibility, visual, performance, evidence | render/state/keyboard/responsive/console |
| `RESEARCH_REPORT` | source quality, freshness, correctness, evidence, efficiency | primary citations, date, source matrix |
| `GAME_RUNTIME` | gameplay correctness, visual/readability, performance, accessibility where relevant, evidence | playtest, asset/runtime, input, perf |
| `HIGH_RISK` | all exposed dimensions + authority/recovery | security, failure-first, independent review, residual risk |
| `DOCUMENTATION_ARCHITECTURE` | completeness, coherence, traceability, source accuracy, usability, evidence | link/count/consistency/independent audit |

## Scoring

Scores são auxiliares. Use anchors coarse (FAIL, major revision, acceptable, reference candidate) e confidence. Um gate required falho não pode ser compensado por average. Para visual/qualitative review, score por região/dimensão só quando artifact evidence existe.

## Product specificity

O reviewer pergunta se o output seria intercambiável com qualquer produto/domínio. Corrigir com domain-native content, constraints, workflows, material, state e tool evidence; não com decoração genérica. A definição visual do design-director é uma inspiração de método, não um score universal.

## Evidence confidence

`HIGH`: boundary real + procedure current + artifact resolve; `MEDIUM`: static/reproducible proxy com limitações; `LOW`: inferência/explanation ou amostra pequena. Confidence não altera status automaticamente.
