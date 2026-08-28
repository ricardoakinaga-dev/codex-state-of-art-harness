# ADR-009 — Codex-native first, provider explicit

**Status:** `PROPOSED` · **Data:** 2026-08-28 · **Escopo:** compatibilidade de host

## Contexto

O host Codex oferece mecanismos públicos como AGENTS.md, Skills, subagents, configuração, tools e MCP; os detalhes internos de matching, loading e estado não são todos observáveis. O audit também encontrou cópia byte-identical de `engineering-framework` em `.agents` e `.codex`, sem host-load trace.

## Decisão

O harness usa primeiro a fronteira nativa observada; Skills descrevem workflow/policy e MCP/provider fornece ação/dados quando necessário. Claims de precedência, load, compaction ou schema futuro ficam `PROPOSED`/`UNKNOWN` até medidos. Duplicatas recebem policy explícita e validação controlada antes de convergência.

## Alternativas consideradas

- Emular toda a plataforma no repo: runtime leakage e lock-in.
- Tratar provider como capability universal: inventa disponibilidade.
- Escolher uma cópia sem trace: pode gerar autoridade silenciosa.

## Consequências

O design permanece portátil e honesto, mas depende de adapters e de futuras observações do host. Nenhuma configuração global é alterada nesta fase.

## Evidência

Documentação oficial de [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Skills](https://learn.chatgpt.com/docs/build-skills), [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) e `skill-audit/reports/03-static-audit.md`/`13-authority-model.md`.

## Revalidação

Instrumentar controlled host-load trace e confirmar precedência real em instalação limpa antes de definir canonical path ou remover duplicata.
