# 32 — Research Director

## Missão

Compor current lookup, documentation lookup, deep synthesis e decision framing sem transformar todo pedido em pesquisa profunda ou em competição entre providers.

## Layers

| Layer | Responsibility | Activation |
| --- | --- | --- |
| Research Director | define question, scope, source quality, freshness, synthesis need | multi-source/current decision |
| Researcher | plan queries, compare, cite, track uncertainty | research evidence needed |
| Official docs route | authoritative product/API/framework behavior | named/current official source |
| Provider | execute search/fetch | provider available/authorized |
| Synthesis | combine findings and implications | comparison/decision output |
| Market research | market/competitive/investor decision | business question |
| Verification | check citations/claims/freshness | every material report |

## Composition

```text
research-director
  → choose source policy
  → choose one provider route (native web / Exa / Context7 / official)
  → fetch current primary sources
  → synthesize only if required
  → verify claims, dates, quotes and limitations
```

`deep-research` is synthesis workflow, `exa-search` is provider, `documentation-lookup` is library/framework docs route, `openai-docs` is official OpenAI route, `market-research` frames business decisions. They are complementary only with explicit contracts.

## Provider competition rule

Do not call native web, Exa, Firecrawl, Context7 and market route in parallel for a single lookup unless the hypothesis is provider comparison and cost/quality/latency are measured. Prefer official primary source for OpenAI/product behavior. For current facts, record retrieved_at and source URL.

## Output contract

Question, scope, source matrix, claims, citation per claim, freshness, confidence, conflicting sources, assumptions, unknowns, synthesis/implications, methods, provider/tool events, and next validation. A search snippet or model memory is not sufficient.

## Failures

Provider unavailable → authorized fallback or `BLOCKED`; stale source → label and search again; conflicting primary docs → preserve conflict and ask/route; missing citation → claim remains `UNKNOWN`; excessive scope → narrow question before adding providers.

## Codex-native boundary

O Director não inventa Context7/Exa/native web availability. O host and MCP configuration determine callable tools; Skills explain workflow and quality, while MCP supplies live data/actions according to official docs.
