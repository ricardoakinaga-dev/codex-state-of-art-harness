# 28 — Domain Directors Roadmap

## Regra

Directors são poucos e justificados por decisões/quality profiles distintos. Um Director coordena um domínio; não é uma camada obrigatória para cada specialist. Todos continuam sujeitos ao authority model e às gates do Harness.

## Roadmap

| Director | Missão | Boundaries | Specialists | Quality profile | Tools | Assurance |
| --- | --- | --- | --- | --- | --- | --- |
| `engineering-director` | transformar problema técnico em implementação verificável | source, API, data, runtime, tests | backend, frontend, API, security, database, performance | correctness/reliability/security/maintainability | shell, test, browser, docs | verification + review + gauntlet por risk |
| `design-director` | dirigir outcome visual acessível e específico | visual thesis, UI, assets, visual QA | UX, design system, frontend visual, image, game art | visual/UX/accessibility/fidelity | browser, imagegen, SVG, Figma when available | render ledger + independent visual critic |
| `research-director` | compor busca, source quality e synthesis | evidence/current facts/decision report | researcher, provider, docs, market | freshness/accuracy/provenance | official web, Context7, Exa, native search | citation audit + blind source review |
| `game-director` | integrar game loop, systems, art e playtest | player outcome/runtime readability | gameplay, art, level, physics, AI, VFX, audio | playability/readability/performance | browser/game runtime, asset tools | playtest + performance + critic |
| `data-director` | governar data products, schemas e analysis | data lifecycle, quality, privacy | database, analytics, visualization, migration | integrity/privacy/reproducibility | SQL, parsers, notebooks, validators | data review + recovery |
| `infrastructure-director` | operar deployment/runtime/reliability com autoridade | hosts, network, containers, observability | platform, SRE, security, release | availability/recovery/security | shell, logs, metrics, cloud tools | incident/recovery/security review |

## Activation

Route on boundary and deliverable. Uma tarefa pode usar dois Directors (ex.: design + engineering) somente com ownership explícito e um Integrator. Não ativar todos por “projeto grande”.

## Promotion criteria

Um Director futuro precisa de: scope testável, manifest, composition contracts, minimum route, do-not route, quality profile, known-bad eval, deterministic checks, failure/degradation, stop conditions, tool preflight, independent review e evidence de valor/custo.

## Unresolved dependency

O design-director referencia specialists visuais/game/Figma que não estão confirmados como callable no ambiente observado. O roadmap registra isso como `UNKNOWN`; não os trata como instalados. Veja [`30-design-director-integration.md`](./30-design-director-integration.md).
