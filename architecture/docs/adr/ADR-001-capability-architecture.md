# ADR-001 — Capability architecture

**Status:** `PROPOSED` · **Data:** 2026-08-28 · **Escopo:** arquitetura documental

## Contexto

O workspace observado contém Skills úteis, mas a topologia é plana: tipos, escopos, dependências e composição não são um contrato único. Isso favorece colisão, ativação redundante e fronteiras ambíguas.

## Decisão

Modelar o futuro harness como camadas explícitas — Router, Director, Orchestrator, Specialist, Tool/Provider, Verification, Reviewer, Assurance, Registry, State, Artifact e Telemetry — com um `CapabilityManifest` e contracts versionados. Cada camada terá um reason-to-exist, autoridade, input/output e failure mode documentados.

## Alternativas consideradas

- Manter Skills como catálogo plano: baixo custo imediato, mas preserva a ambiguidade auditada.
- Criar um único mega-agent: reduz handoffs, porém mistura decisão, execução e prova.
- Copiar todas as Skills para subpackages: aumenta duplicação e não resolve autoridade.

## Consequências

Há custo de modelagem e registry, mas routing, composição e avaliação passam a ser observáveis. A arquitetura é proposta; não há runtime criado nesta fase.

## Evidência

`references/skill-audit/reports/02-functional-classification.md`, `03-static-audit.md`, `16-capability-stack-v2.md` e `19-contracts.md` sustentam o diagnóstico local.

## Revalidação

Revalidar no primeiro vertical slice com route trace, contract tests e comparação no-skill/routed. Superseder exige evidência de menor ambiguidade sem regressão de qualidade.
