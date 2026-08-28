# ADR-006 — Progressive disclosure por camadas

**Status:** `PROPOSED` · **Data:** 2026-08-28 · **Escopo:** contexto

## Contexto

O corpus atual inclui dezenas de Skills e referências; carregar tudo em toda solicitação aumenta ruído, tokens e collisions. A documentação oficial do Codex descreve metadata-first para Skills, mas não expõe um contrato universal de budgets ou matching causal.

## Decisão

Organizar contexto em L0 task/authority, L1 profile/route, L2 manifest e contratos, L3 `SKILL.md`/playbook, L4 referências e scripts específicos, L5 evidence/raw artifacts. Carregar apenas o mínimo que satisfaz a rota e registrar o que foi selecionado, loaded/unknown e omitido.

## Alternativas consideradas

- Injetar corpus completo: fácil, caro e difícil de auditar.
- Usar apenas descrição curta: barato, mas insuficiente para workflow/gates.
- Deixar cada capability escolher contexto sem policy: conflito e duplicação.

## Consequências

Registry e invalidation se tornam necessários. A camada L0–L2 continua pequena; referências profundas são puxadas por necessidade e freshness.

## Evidência

`docs/16-context-management.md`, `docs/11-skill-md-standard.md` e documentação oficial de Skills consultada em 2026-08-28.

## Revalidação

Comparar context cost, miss rate, quality e latency entre progressive e full-context em workload fixo.
