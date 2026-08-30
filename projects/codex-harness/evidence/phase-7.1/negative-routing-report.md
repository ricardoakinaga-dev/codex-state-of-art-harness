# Negative routing and overengineering report

O catálogo determinístico Phase 7 passou 48/48 cenários. Os três cenários de
negative routing bloquearam README, estilo/button e configuração sem backend;
os cenários de backend selecionaram a rota especialista. Os cenários de
overengineering, scope creep, migration, transaction, tool escalation,
prompt-injection, stale evidence e review separation mantiveram os stops
esperados (`NO_BACKEND_BOUNDARY`, `SCOPE_EXPANSION_REQUIRED`,
`MISSING_REQUIRED_TOOL`, `STALE_INPUT` ou `HUMAN_DECISION_REQUIRED`).

Não foi introduzida nova camada, repository pattern, CQRS, event bus ou
migration fora do fixture.
