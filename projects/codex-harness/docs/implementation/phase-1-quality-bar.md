# Fase 1 — Quality Bar congelada

**Versão:** P1-QB-1
**Congelada em:** 2026-08-28
**Veredito máximo:** `Phase 1 Kernel implementation PASS`

| ID | Critério | Evidência obrigatória | Tipo |
| --- | --- | --- | --- |
| P1-CONTRACT | Os 12 records conceituais têm tipos, versão, envelope, invariantes, validação e JSON determinístico | testes de contrato, schema report e fixtures | bloqueante |
| P1-REGISTRY | Manifestos registram/listam/inspecionam, resolvem versão/dependência, detectam ciclo/conflito/stale/proveniência e nunca executam | testes de registry e report | bloqueante |
| P1-CLASS | Profile normaliza e classifica seis dimensões com razão, confiança, evidência e desconhecidos | testes golden/negative | bloqueante |
| P1-ROUTE | RouteDecision e política mínima cobrem direto, especialista, composição, provider, degraded, bloqueio e fallback | testes de routing | bloqueante |
| P1-AUTH | Dono, escopo e poderes de bloqueio/retry/replan/finalize são verificáveis; autoaprovação é rejeitada | testes negativos e security report | bloqueante |
| P1-EVID | Claim → procedure → evidence é rastreável; freshness e artefatos/lineage propagam stale | testes de evidência/lineage | bloqueante |
| P1-STATE | Transições válidas passam e inválidas falham; status multidimensional não colapsa em um campo | testes de estado | bloqueante |
| P1-STOP | As nove condições de stop e progresso/no-progress/repeated-failure/oscillation/budget são detectáveis | testes de stop engine | bloqueante |
| P1-TELEM | Eventos versionados, append-only, redacted e encadeados; `CAPABILITY_LOADED` exige observação | testes de telemetria e privacy | bloqueante |
| P1-ISOLATION | `.harness/` contém layout local e não há escrita em Skills/global config/submódulo | layout scan e security report | bloqueante |
| P1-CLI | `validate`, `registry list/inspect`, `profile`, `route`, `state` e `telemetry validate` funcionam; `run` não existe | smoke/integration tests | bloqueante |
| P1-QUALITY | format, lint, typecheck, unit/integration/golden/negative e coverage core ≥ 80% | comandos reais e outputs | bloqueante |
| P1-SECURITY | Sem secrets, eval/pickle/import dinâmico, traversal; entradas são validadas e erros não vazam dados | scan + revisão adversarial | bloqueante |
| P1-REPORT | relatório de implementação, deferred scope e pacote de evidências existem | inventory | bloqueante |
| P1-PERF | microbenchmarks baseline dos caminhos de validação e serialização são registrados | benchmark JSON | informativo |

## Regras de veredito

`PASS` exige todos os critérios bloqueantes com evidência atual e nenhuma
finding Critical/High aberta. Ausência de uma medição é uma limitação explícita,
não uma aprovação implícita. O resultado não autoriza declarar harness completo,
produção, AAA verificado, orquestração autônoma ou modernização de Skills.
