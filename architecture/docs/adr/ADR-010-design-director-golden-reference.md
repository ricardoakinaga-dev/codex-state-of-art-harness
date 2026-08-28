# ADR-010 — Design Director como golden reference delimitado

**Status:** `PROPOSED` · **Data:** 2026-08-28 · **Escopo:** integração visual

## Contexto

O pacote local `design-director` apresenta uma pipeline visual disciplinada: direction, medium choice, source of truth, rendered inspection, critic, evidence ledger e bounded iteration. Seu escopo declarado é visual; não prova um padrão geral para backend, research ou runtime.

## Decisão

Preservar esses padrões como golden reference para design e adaptar apenas contratos transferíveis: brief, medium, acceptance evidence, critic independente, visual QA, provenance e iteration budget. Frontend, imagegen, game e data visualization mantêm fronteiras próprias; diferenças e unknowns ficam registrados.

## Alternativas consideradas

- Copiar o pacote inteiro para todos os domínios: generalização indevida.
- Ignorar o pacote: perde o exemplo local mais maduro.
- Tratar visual score como qualidade global: mistura dimensões não equivalentes.

## Consequências

Design torna-se piloto de integração e frontend recebe um visual contract claro. A promoção para Directors gerais exige evals domain-specific e não pode ser inferida da referência visual.

## Evidência

`docs/30-design-director-integration.md`, `docs/21-quality-model.md` e o `SKILL.md`/references/evals locais do `design-director`.

## Revalidação

Comparar fidelity/interaction evidence, false confidence e context cost em casos visuais; registrar o que não transfere para outros domínios.
