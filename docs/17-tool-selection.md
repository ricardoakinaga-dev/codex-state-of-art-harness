# 17 — Tool Selection

## Regra

Escolher o meio/tool deliberadamente pelo output e pela boundary. Reasoning é adequado para estratégia/ambiguidade; ferramentas são preferidas para observação, transformação e checks que podem ser deterministicamente executados.

## Matriz

| Necessidade | Primeiro | Fallback | Não fazer |
| --- | --- | --- | --- |
| editar arquivo | patch/supported file tool | shell seguro autorizado | reescrever arquivos amplos sem inspeção |
| explorar repo | `rg`, inventory, parser | find/read targeted | contexto inteiro |
| current official fact | OpenAI official docs/native web | provider autorizado | memória sem freshness |
| library/framework docs | Context7/documentation provider | official web | inventar API |
| browser/render | Browser/IAB/Playwright | static inspection com limitation | alegar UX por source code |
| image asset | native image generation quando disponível | provider explícito | rasterizar UI text |
| schema/links | validator/parser | structured manual review | keyword-only proof |
| quality challenge | fresh reviewer/gauntlet | separated self-review | builder self-approval |
| parallel work | native subagent workflow | serial logical lanes | dmux/other harness by default |
| media provider | exact provider requested/allowed | compatible native route | provider competition sem hipótese |

## Tool preflight

Antes de invocar, confirmar disponibilidade, versão/endpoint, authentication state sem expor secret, permission, expected input/output, timeout, cost, idempotence e evidence artifact. Um nome presente em Skill/reference não prova que a tool está callable.

## Fallback

Fallback deve preservar o claim possível e reduzir o claim impossível. Exemplo: sem browser, pode validar link/schema/structure, mas não pode afirmar responsive visual/interaction. Sem provider de pesquisa, pode parar ou usar fonte autorizada; não inventar freshness.

## Falha de tool

Classificar timeout/auth/schema/permission/provider. Retry só se seguro/idempotente e com budget. Registrar raw error, affected scope, fallback, confidence e limitation.

## Native-Codex first

Skills acrescentam workflow, contracts, source-quality, routing e quality policy. Native shell/patch/web/MCP/browser/imagegen/subagent permanece a autoridade de execução quando disponível. Uma Skill não deve afirmar que criou um tool que o host não fornece.

## Provider preference

Provider explicitamente pedido recebe consideração após safety. Para pesquisa, escolher um provider adequado ao freshness/coverage; synthesis (`deep-research`/market) só entra quando o deliverable exige. Para media, output format e provider auth decidem. Equivalência entre providers precisa de benchmark, não de opinião.
