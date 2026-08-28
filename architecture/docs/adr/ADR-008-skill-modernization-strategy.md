# ADR-008 — Modernização incremental com preservação de evidência

**Status:** `PROPOSED` · **Data:** 2026-08-28 · **Escopo:** evolução

## Contexto

O catálogo contém capacidades fortes e duplicações; reescrita em massa poderia apagar provenance, regressões e especializações. Há ainda dependências opcionais não resolvidas no audit.

## Decisão

Modernizar por waves: inventário, upstream/current comparison, fronteira Codex-native, contracts, workflow, deterministic checks, evals, known-bad, benchmark e promotion/rejection record. Um pacote só sobe de status com evidence; não se instala substituto nem modifica Skill existente nesta fase.

## Alternativas consideradas

- Reescrever tudo para um padrão único: perda de contexto e alto blast radius.
- Promover por similaridade lexical: não prova valor.
- Congelar catálogo: preserva dívida e colisões.

## Consequências

O roadmap é mais lento, mas reversible e auditável. Engineering core é piloto natural; design-director é referência visual, não template universal.

## Evidência

`docs/33-skill-modernization-program.md`, `docs/34-modernization-template.md`, `references/skill-audit/reports/18-priority-roadmap.md` e `references/skill-audit/reports/19-contracts.md`.

## Revalidação

Cada wave deve publicar delta, eval/benchmark, open risks, compatibility e decisão de promoção. Falha em gate mantém pacote candidate/rejected.
