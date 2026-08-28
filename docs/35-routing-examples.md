# 35 — Routing Examples

As rotas abaixo são exemplos `PROPOSED` para testes de regressão. “Activated” é o mínimo esperado, não uma lista universal. Os nomes são capability IDs candidatos: preflight precisa provar que estão instalados/callable; se não estiverem, a decisão de route vira `FALLBACK` ou `BLOCKED` com `reason_code=UNAVAILABLE`; uma execução que continua pode ter lifecycle/artifact `PARTIAL` com limitation. Cada caso deve ser convertido em cenário com fixture, known-bad e oracle antes de usar métricas.

| # | Pedido / task profile | Route | Activated | Not activated by default | Quality gates |
| ---: | --- | --- | --- | --- | --- |
| 1 | corrigir typo em README; trivial/local/low | DIRECT | none | directors, orchestrator, gauntlet, research | diff, link/local check |
| 2 | mudar um label de UI; trivial/visual supporting | DIRECT | frontend check | engineering-director, design-director, gauntlet | render smoke if available, diff |
| 3 | renomear variável interna; small/module/low | DIRECT + specialist | coding baseline | orchestrator, deep-research | unit/type/lint |
| 4 | corrigir bug CSS isolado; small/visual material | SMALL VISUAL | frontend + verification | backend, API, orchestration | screenshot/state, accessibility smoke |
| 5 | ajustar breakpoint com regressão; small/frontend | SMALL VISUAL | frontend + visual QA | backend, research | 375/768/1440 or project widths, keyboard |
| 6 | adicionar endpoint REST; medium/service | MEDIUM API | api + backend + verification | media, deep research, orchestrator | schema/validation/auth/integration |
| 7 | adicionar endpoint paginado `/api/v1/users`; medium/data | MEDIUM API | api + backend + security + verification | design, game, gauntlet | pagination/status/error/auth/regression |
| 8 | corrigir validação de input; medium/security boundary | SECURITY FIX | security + backend + verification | orchestration unless lanes | known-bad input, authz, regression |
| 9 | refatorar auth em um módulo; large/security | DIRECTED SECURITY | engineering-director + security + verification + review | media/research; orchestrator conditional | threat/authz/session/regression |
| 10 | refatorar auth multi-service; critical/cross-system | CRITICAL | engineering-director + security + orchestrator + verification + independent assurance | generic TDD by default | authority, failure-first, recovery, re-audit |
| 11 | criar landing page premium; large/high visual | VISUAL PRODUCT | design-director + frontend + verification + visual critic | backend/security unless boundary | render, responsive, a11y, specificity |
| 12 | criar dashboard operacional; large/UX/data | DASHBOARD | design-director + frontend + data + verification | imagegen unless asset needed | data semantics, states, keyboard, render |
| 13 | criar jogo de corrida browser; large/high-fidelity | GAME | game-director + gameplay + game-ui + playtest + verification | market research, API unless needed | input, loop, runtime, performance, playtest |
| 14 | corrigir colisão física; medium/game | GAME BUG | gameplay/physics + verification | art director, orchestration | deterministic scenario, regression |
| 15 | criar sprite de personagem; medium/visual asset | ASSET | game-art + asset-pipeline + design-director optional | backend, E2E | provenance, dimensions, runtime readability |
| 16 | pesquisar API atual; small/current | RESEARCH LOOKUP | researcher + one official/provider route + verification | market/deep synthesis | freshness, primary citation, scope |
| 17 | comparar três APIs e recomendar uma; medium/research | RESEARCH SYNTHESIS | research-director + researcher + provider + verification | multiple providers without hypothesis | source matrix, trade-offs, citations |
| 18 | pesquisar documentação atual de React; small/current docs | DOCS LOOKUP | documentation-lookup + official docs + verification | deep-research, market | version/freshness/citation |
| 19 | fazer market sizing com fontes; large/business | MARKET RESEARCH | research-director + market-research + researcher + review | engineering/code specialists | source quality, assumptions, sensitivity |
| 20 | fazer revisão de segurança de diff; large/high risk | SECURITY REVIEW | security + verification + reviewer | orchestrator unless separable lanes | threat matrix, input/auth/secret, findings |
| 21 | preparar review pesado de mudança multi-file; large | ASSURANCE | verification + gauntlet + review | orchestrator unless independent lanes | bar, regression, independent critique, stop |
| 22 | executar teste E2E de login; medium/user impact | BROWSER FLOW | e2e + security + verification | gauntlet unless high risk | real flow, authz, recovery, console |
| 23 | escrever unit tests para função; small | TEST TACTIC | tdd optional + verification | E2E, orchestrator, gauntlet | red/green, focused regression |
| 24 | adicionar feature multi-module; large | ENGINEERING | engineering-director + planner + relevant specialists + verification | every specialist | acceptance, integration, risk-shaped tests |
| 25 | migrar schema sem downtime; critical/data | MIGRATION | data-director + database + security + orchestrator + verification + assurance | visual/media | mixed-version, recovery, authority |
| 26 | corrigir query lenta; medium/performance | PERFORMANCE | backend/database/performance + verification | design, deep-research | representative p95/query plan/regression |
| 27 | criar componente acessível; medium/frontend | ACCESSIBLE UI | frontend + accessibility + verification | game, media, orchestration | semantics, keyboard, focus, contrast, responsive |
| 28 | gerar imagem hero; medium/asset | IMAGE | design-director + imagegen/native image tool | frontend implementation unless requested | prompt/identity/crop/provenance/inspection |
| 29 | editar vídeo existente; large/media | VIDEO EDIT | video-editing + provider only if selected + verification | design-director unless visual product context | source, timeline, export, audio/provenance |
| 30 | produzir carrossel social; medium/content | CONTENT | content-engine + graphic optional | crosspost/x-api unless distribution requested | voice, claims, platform format |
| 31 | adaptar um texto para X/LinkedIn; small/distribution | CROSSPOST | crosspost consuming source + verification | content generation, x-api if no post requested | platform fit, no duplicate copy, claims |
| 32 | postar via X API; medium/integration | PROVIDER ACTION | x-api + security + verification | content-engine if copy supplied | OAuth, rate, idempotence, audit |
| 33 | criar deck HTML; large/visual | PRESENTATION | frontend-slides + design-director + verification | backend, game | viewport, keyboard, reduced motion, content |
| 34 | atualizar runtime Bun; medium/runtime | RUNTIME | bun-runtime + backend/frontend relevant + verification | research unless current docs needed | version/lockfile/build/test |
| 35 | atualizar Next/Turbopack; medium/runtime | RUNTIME | nextjs-turbopack + frontend + documentation-lookup if current | media, orchestrator by default | version/build/perf/regression |
| 36 | criar nova capability package; large/control | CAPABILITY AUTHORING | skill-creator + capability validator + eval-harness + reviewer | runtime implementation | manifest, links, known-bad, promotion gate |
| 37 | modernizar Skill Claude-oriented; large/migration | MODERNIZATION | capability Director + research/docs + eval-harness + independent review | blind upstream merge | portability, contract, A/B, provenance |
| 38 | instalar Skill de terceiro; medium/permission | EXPLICIT INSTALL | skill-installer/plugin policy + security review | implicit broad activation | source/provenance, permission, package validation |
| 39 | alterar MCP server config; critical/ops | CONTROLLED CONFIG | infrastructure-director + security + verification + human authority | direct casual edit | trust, config precedence, rollback, audit |
| 40 | investigar falha de provider sem mudar código; medium/audit | DIAGNOSTIC | provider + verification + audit | orchestrator, repair builder | raw error, scope, fallback/unknown |

## Leitura dos exemplos

Os casos 1–5 devem provar que tarefas simples continuam simples. Casos 9–10 e 25, 32, 39 provam que risk/authority escalam independente de line count. Casos 11–15 e 27–29 provam que visual/game/media routing é output-aware. Casos 16–19 provam que provider e synthesis não são sinônimos. Casos 21, 36–37 provam que assurance/modernization precisam de evidence e não só prompts longos.

## Oracle mínimo

Para cada exemplo, o evaluator compara: `actual activated`, `minimum justified`, `forbidden overactivation`, `required gates`, context/cost, artifact/evidence e final claim. O julgamento “route correta” é adjudicado antes do run e não reescrito para acomodar o resultado.
