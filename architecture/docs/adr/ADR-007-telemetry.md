# ADR-007 — Telemetria causal, append-only e privacy-aware

**Status:** `PROPOSED` · **Data:** 2026-08-28 · **Escopo:** observabilidade

## Contexto

O audit local não demonstrou host-load trace; sem distinguir selected, loaded, tool calls, context e quality não é possível atribuir causa a uma Skill. Telemetry pode ainda expor prompts, secrets ou PII.

## Decisão

Registrar eventos correlacionados, append-only e versionados, com route, load quando observado, tool/provider, budgets, resultado, evidence, baseline, privacy class e limitações. Raw sensível é redacted/minimizado. Event loss ou reorder aparece como limitation e pode bloquear claim causal.

## Alternativas consideradas

- Apenas log final: não explica decisões nem custo.
- Self-report da capability: não prova load do host.
- Log bruto completo: maior risco e baixa governança.

## Consequências

Há custo de instrumentação e retenção, mas evals de routing e qualidade se tornam defensáveis. Política de acesso/retention permanece decisão de implementação/governança.

## Evidência

`docs/18-telemetry.md`, `docs/19-observability.md`, `docs/contracts/TelemetryEvent.json.md` e `references/skill-audit/reports/18-priority-roadmap.md`.

## Revalidação

Provar causalidade em experimento controlado selected/loaded/no-skill, com dados minimizados e auditoria de perda de eventos.
