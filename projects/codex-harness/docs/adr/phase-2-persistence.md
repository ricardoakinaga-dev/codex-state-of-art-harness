# ADR P2-003 — Persistence local append-oriented

## Decisão

Persistence é opcional para a pure core e, quando usada pela CLI, grava apenas
em `.harness/state/`, `.harness/evidence/` e `.harness/telemetry/`. JSON e JSONL
são inspectáveis; writes são atômicos, limites são aplicados e cada record
carrega run/invocation/node ownership. Não há banco, daemon ou store global.

## Consequências

Recovery consegue separar run finished, unfinished e corrupt sem afirmar
sucesso. Durabilidade, locking multi-processo e retenção de produção ficam
deferidos.
