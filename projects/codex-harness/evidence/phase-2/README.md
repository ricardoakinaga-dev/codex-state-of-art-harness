# Evidências — Fase 2

Este pacote prova somente o `PHASE2-001`: execution kernel project-local,
determinístico e bounded. Cada execução usa providers fixtures registrados e
não tem autoridade para carregar Skills, subagentes, MCP, shell, rede,
credenciais, host internals ou configuração global.

## Índice

- [execution-contract-report.md](./execution-contract-report.md)
- [state-machine-report.md](./state-machine-report.md)
- [graph-validation-report.md](./graph-validation-report.md)
- [authority-enforcement-report.md](./authority-enforcement-report.md)
- [provider-report.md](./provider-report.md)
- [verification-report.md](./verification-report.md)
- [telemetry-report.md](./telemetry-report.md)
- [cli-report.md](./cli-report.md)
- [security-summary.md](./security-summary.md)
- [coverage-report.md](./coverage-report.md)
- [lint-report.md](./lint-report.md)
- [typecheck-report.md](./typecheck-report.md)
- [benchmark-summary.json](./benchmark-summary.json)
- [independent-review.md](./independent-review.md)
- [readiness.json](./readiness.json)
- [final-readiness.md](./final-readiness.md)
- [final-report.md](./final-report.md)

## Cenários golden

| Cenário | Resultado provado |
| --- | --- |
| A — direct success | provider local, artifact, evidence, verification, assurance e delivery |
| B — authority deny | deny tipado antes de resolver/chamar provider |
| C — graph success | DAG acíclico em ordem topológica determinística |
| D — dependency failure | falha preservada, descendente bloqueado, independente preservado |
| E — timeout | `TIMED_OUT` sem artifact de saída |
| F — cancellation | cancelamento durante fixture lento, uma chamada iniciada e sem artifact |
| G — verification failure | output/artifact forged não promove quality |
| H — partial | partial permanece partial e não é delivery |
| I — stop-before | stop policy bloqueia antes da chamada |
| J — repair success | repair explícito, bounded e ligado à causa |
| K — repair exhausted | limite de reparos termina em failure sem fallback |
| L — stale evidence | freshness stale falha verification/assurance |

Os cenários são exercitados pelos testes `test_phase2_execution_paths.py`,
`test_phase2_kernel.py` e `test_phase2_adversarial.py`; os testes existentes da
Fase 1 permanecem parte da suíte completa.

## Resultado atual

A rodada local final passou em 232 testes, com 85% de cobertura total, Ruff,
mypy, 34 testes de integração CLI, benchmark `P2-BENCH-1` e scans de
segurança. Três reviewers read-only encontraram bloqueios antes do hardening;
uma crítica read-only pós-hardening encontrou três achados adicionais, todos
corrigidos e retestados. A confirmação independente final contra o pacote atual
teve uma tentativa read-only adicional (`CONDITIONAL_PASS`), sem novo defeito
de implementação; como a reconciliação posterior alterou os bytes do pacote,
a aprovação do pacote exato ainda está pendente. O status permanece `CONDITIONAL PASS` e nenhum gate
`PHASE2-VERIFIED` é alegado.

## Limitações assumidas

Não há adapter real do Codex, execução de código de terceiros, subprocesso,
rede, persistência multi-processo com locking, fan-out concorrente, SLO de
produção ou alegação `AAA_VERIFIED`. O benchmark é baseline local, não mede
qualidade causal nem latência de produção.
