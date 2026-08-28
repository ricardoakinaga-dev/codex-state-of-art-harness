# 33 — Current Skill Modernization Program

## Objetivo

Modernizar Skills existentes para a arquitetura de capability sem apagar evidência, reescrever automaticamente ou instalar substitutos. Cada wave começa por inspect current/upstream, aplica contracts e passa por eval/benchmark antes de promoção.

## Estados do programa

- `CURRENT`: snapshot instalado observado; não significa recomendado.
- `UPSTREAM`: fonte a ser inspecionada/revalidada; “mais novo” não significa melhor.
- `VNEXT`: proposta Codex-native de boundary, disclosure, tools e evidence.
- `PROMOTION CRITERIA`: gates para aceitar, manter candidate, rejeitar ou deferir.

## WAVE 1 — Engineering Core

| Skill | CURRENT | UPSTREAM | VNEXT | Promotion criteria |
| --- | --- | --- | --- | --- |
| `backend-patterns` | backend Node/Express/Next, overlap API/security | revalidar source/version e APIs atuais | specialist backend com boundary/data/error/evidence | backend eval, no secret/input gaps, route precision |
| `frontend-patterns` | React/Next broad, high context | revalidar framework guidance | frontend specialist, state/perf/accessibility conditional | runtime flow + responsive/a11y + cost |
| `api-design` | REST contracts/status/pagination/versioning | verify current standards | API specialist separate from implementation | schema/error/auth/idempotency eval |
| `security-review` | auth/input/secrets/payment sensitivity | verify security guidance | trust-boundary overlay and human-stop policy | threat fixtures, no critical, independent review |
| `tdd-workflow` | universal 80% unit/integration/E2E wording | compare current testing policy | proportional test tactic by profile | known-small route bypass + high-risk coverage |
| `e2e-testing` | Playwright/POM/CI/flakiness | verify current Playwright API | critical-flow overlay with public-boundary evidence | real browser flow, artifact, no mock-only pass |
| `verification-loop` | broad Claude-oriented verification | inspect upstream/current Codex affordances | canonical evidence owner with schema/ledger | current evidence, stale invalidation, route tests |
| `coding-standards` | cross-project baseline | compare repository conventions | narrow shared floor, no duplicate specialist rules | collision scan, low context cost |
| `eval-harness` | EDD for Claude Code, `.claude` assumptions | inspect latest eval approaches | Codex-native scenario/fixture/oracle layer | routing/capability/harness regression suite |

## WAVE 2 — Research

| Skill | CURRENT | UPSTREAM | VNEXT | Promotion criteria |
| --- | --- | --- | --- | --- |
| `deep-research` | multi-source Firecrawl/Exa synthesis | revalidate providers/source policy | synthesis layer after provider selection | citation/freshness/overbreadth eval |
| `documentation-lookup` | Context7 current docs route | revalidate Context7 contract | docs provider overlay with official-source preference | known-current API tests, fallback |
| `exa-search` | Exa MCP neural search | inspect tool schema/auth drift | explicit provider capability | provider preflight + source quality |
| `market-research` | decision-oriented market/competitor research | revalidate data/source limits | domain specialist using research-director | citation, bias, decision utility |

## WAVE 3 — Creative

| Skill | CURRENT | UPSTREAM | VNEXT | Promotion criteria |
| --- | --- | --- | --- | --- |
| `graphic-creation` | broad any-graphic trigger | compare native image/design routing | narrow output-type router | false-positive/quality/evidence eval |
| `imagegen` | native image generation/edit guidance | verify current image tool contract | asset specialist under design/game Directors | provenance, native-size inspection, identity gate |
| `fal-ai-media` | provider-specific image/video/audio | verify MCP/API/model drift | provider only, never generic media Director | auth/preflight/fallback/asset eval |
| `video-editing` | real-footage pipeline with many tools | verify FFmpeg/Remotion/provider currentness | editing specialist with source/provenance | boundary/codec/timeline checks |
| `content-engine` | source platform-native content | inspect current channel policies | content source capability | voice/product-truth/human-review eval |
| `article-writing` | long-form voice/credibility | revalidate source/brand dependency | writing specialist consumes brief | factuality/voice/structure review |
| `crosspost` | adapts source content across platforms | verify platform rules | distribution adapter after content source | no-duplicate adaptation + API optional |
| `frontend-slides` | animation-rich browser decks | revalidate browser/visual refs | presentation specialist + design visual QA | viewport/interaction/accessibility |

## WAVE 4 — Providers / Runtime

| Skill | CURRENT | UPSTREAM | VNEXT | Promotion criteria |
| --- | --- | --- | --- | --- |
| `claude-api` | Anthropic API/SDK integration | verify official Anthropic source separately | explicit external provider adapter | secret boundary, schema/current API |
| `elevenlabs-api` | backend-safe audio API guidance | revalidate API/voice/schema | explicit audio provider | secret/no frontend exposure + audio artifact |
| `x-api` | X API posting/read/analytics | revalidate OAuth/rate policy | explicit distribution provider | OAuth/rate/audit/idempotency |
| `nextjs-turbopack` | version-gated Next/Turbopack guidance | verify current Next docs | runtime specialist activated by stack/version | version fixture, no stale claims |
| `bun-runtime` | Bun runtime/package/bundler/test guidance | verify current Bun/Vercel docs | runtime specialist only when Bun detected | version/lockfile/build benchmark |

## Cross-wave promotion rules

No wave can promote a package if owner/trigger/conflict/stop/evidence is absent, a provider dependency is unverified, a known-bad scenario passes, or a Critical finding remains. Preserve original installed sources and record proposed vNext separately until benchmark approval.

## Current limitations

Local audit finds portability debt, optional missing references, duplicate `engineering-framework` and no causal host-load trace. These are program inputs, not permission to edit installed packages: [`skill-audit/reports/14-custom-skills-audit.md`](../skill-audit/reports/14-custom-skills-audit.md), [`05-dependency-graph.md`](../skill-audit/reports/05-dependency-graph.md).
