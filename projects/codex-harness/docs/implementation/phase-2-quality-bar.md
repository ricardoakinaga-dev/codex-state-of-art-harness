# Fase 2 — Quality Bar congelada

**Versão:** P2-QB-1
**Congelada em:** 2026-08-28
**Escopo:** `PHASE2-001` — Execution Kernel local, determinístico e bounded
**Veredito máximo:** `PASS_WITH_LIMITATIONS`

Esta barra autoriza somente a execução de fixtures e providers locais
determinísticos dentro de `projects/codex-harness/`. Ela não autoriza carregar
Skills, subagentes, MCP, shell arbitrário, rede, credenciais, host internals,
deploy, operação de produção ou mutação fora do projeto.

| ID | Critério | Evidência obrigatória | Tipo |
| --- | --- | --- | --- |
| P2-01 | Semântica da Fase 1 permanece compatível; hardening de registry, serialização, estado, autoridade e telemetria tem regressões | `evidence/phase-2/execution-contract-report.md`, testes de regressão | bloqueante |
| P2-02 | A fronteira de projeto rejeita caminhos absolutos, traversal e symlink escape e não escreve em host/global/submódulo | `authority-enforcement-report.md`, `security-summary.md`, testes de segurança | bloqueante |
| P2-03 | `CapabilityInvocation` expõe identidade, operação, origem, dependências, permissões, budget, timeout, acceptance e trace; lifecycle é explícito e legal | `state-machine-report.md`, contratos e testes | bloqueante |
| P2-04 | Provider registry é tipado, imutável, determinístico e distingue registrado, disponível, selecionado e executado; não existe fallback implícito | `provider-report.md`, testes de provider | bloqueante |
| P2-05 | Rota direta é barata e explicável; rota condicional ou bloqueada não executa; provider/capability incompatível não é selecionado | `execution-contract-report.md`, `cli-report.md`, golden tests | bloqueante |
| P2-06 | ExecutionGraph bounded valida IDs, referências, DAG, ciclos, duplicatas, dependências impossíveis, autorização, conflitos, merge, acceptance e budgets | `graph-validation-report.md`, testes de graph | bloqueante |
| P2-07 | Autoridade verifica subject, scope, operation, expiry, conditions, delegation e least privilege antes do provider; deny é resultado de primeira classe | `authority-enforcement-report.md`, testes de autoridade | bloqueante |
| P2-08 | Timeout, cancelamento, budgets de nodes/invocations/retries/tempo/evidence/telemetry e stop-before/between/after verification são enforced | `state-machine-report.md`, `execution-contract-report.md`, golden tests | bloqueante |
| P2-09 | ArtifactRecord tem lineage e digest; EvidenceRecord tem owner, freshness e referências; forged/stale evidence não promove resultado | `verification-report.md`, testes de artifact/evidence | bloqueante |
| P2-10 | Verification é separada da execução; critique/assurance são boundary independente; AAA nunca é inferido apenas de execução | `verification-report.md`, `independent-review.md`, testes de assurance | bloqueante |
| P2-11 | Repair é bounded, preserva partial results e registra tentativa, causa e budget; RunSummary preserva delivery, not-run, unknown, limitações e risco | `execution-contract-report.md`, golden tests | bloqueante |
| P2-12 | Telemetria é estruturada, factual, redacted, append-only, ordenada e failure-tolerant sem corromper o resultado; persistence é local e atômica | `telemetry-report.md`, `security-summary.md`, testes de persistence/telemetry | bloqueante |
| P2-13 | CLI `run`, `--dry-run`, `--json`, `explain`, `quality` e `doctor` têm exit classes estáveis e nunca executam capacidade não registrada | `cli-report.md`, testes de integração | bloqueante |
| P2-14 | Golden scenarios cobrem sucesso direto, deny, graph success/failure, timeout/cancel, verification fail, partial, stop, repair success/exhaustion e stale evidence | `evidence/phase-2/README.md`, `pytest` e fixtures | bloqueante |
| P2-15 | format, lint, mypy, testes, cobertura total ≥ 80% e security checks passam sobre a fonte atual | `coverage-report.md`, `lint-report.md`, `typecheck-report.md`, `security-summary.md` | bloqueante |
| P2-16 | Benchmarks locais medem classificação, registry, route, graph 10/100, provider fixture, serialização, evidence e telemetry; não inventam SLO de produção | `benchmark-summary.json` | obrigatório com limitação explícita |
| P2-17 | Todos os relatórios, readiness JSON, docs de configuração/migração e review independente estão frescos, vinculados ao SHA/dirty state atual | `final-readiness.md`, `final-report.md`, `readiness.json`, `independent-review.md` | bloqueante |

## Regras de decisão

`PASS_WITH_LIMITATIONS` exige todos os critérios bloqueantes evidenciados,
nenhuma finding Critical/High aberta e limitações deferidas explicitamente.
`AAA_VERIFIED` permanece fora da alegação desta fase: o kernel local prova
contratos e fixtures, não o runtime completo do Codex nem qualidade causal.

Qualquer falha em segurança, autorização, integridade, boundary, ciclo,
serialização, freshness ou estado impede aprovação até ser corrigida e
retestada. Um provider indisponível gera `CAPABILITY_UNAVAILABLE` ou
`PROVIDER_UNAVAILABLE`; nunca seleciona fallback por inferência.
