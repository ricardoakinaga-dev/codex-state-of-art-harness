# Codex Capability Harness — HARNESS-SPEC

**Versão documental:** `0.1-proposed` · **Data:** 2026-08-28 · **Fase:** especificação, sem runtime

Este documento é a constituição resumida do futuro harness. Ele define um sistema adaptativo para selecionar, compor, executar e provar capacidades em torno do Codex. Não instala Skill, não altera configuração global, não implementa router/registry/telemetry e não promete comportamento interno que o host não exponha.

## 1. Resultado pretendido

O harness deve transformar uma solicitação em uma execução proporcional: rota direta para trabalho simples; composição explícita para trabalho multi-boundary; evidence suficiente para cada claim; degradação honesta quando uma ferramenta, provider ou subagent não estiver disponível; e parada quando o próximo ciclo não pagar seu custo.

State of Art, aqui, significa cinco propriedades simultâneas: boundary nativo do Codex reconhecido; capabilities com contracts e provenance; decisões observáveis; verificação separada de critique/assurance; evolução por evals e evidence. Triple-A não é adjetivo: é um estado condicionado a gates.

## 2. Problema

O audit local encontrou catálogo plano, colisões de escopo, duplicata byte-identical de `engineering-framework`, lacunas de precedência/load trace, dependências opcionais não resolvidas e routing ainda proxy. O risco é ativar contexto e agentes demais, chamar provider errado, produzir saída genérica ou declarar sucesso sem prova.

## 3. Princípios normativos

1. Autoridade externa precede autoridade interna.
2. A rota mínima que satisfaz o objetivo é o default.
3. Cada componente tem reason-to-exist, boundary e owner.
4. Skills descrevem workflow; ferramentas/MCP/providers fornecem ação ou dados.
5. Director decide estratégia; Orchestrator executa graph; Specialist entrega boundary.
6. Verification relata fatos; Reviewer desafia; Assurance decide continuar/parar.
7. `NOT_RUN`, `UNKNOWN`, partial e residual risk nunca são apagados.
8. Contexto cresce por progressive disclosure, não por injeção total.
9. Retries e iterações são bounded e sujeitos a stop conditions.
10. Modernização preserva source, versões, conflitos e evidência.

## 4. Arquitetura e ciclo

```text
request → TaskProfile → RouteDecision → [direct | Director → ExecutionGraph]
        → specialist/tool/provider execution → ArtifactRecord
        → VerificationReport → CritiqueReport → QualityReport
        → bounded repair or delivery → RunSummary + TelemetryEvent
```

As responsabilidades, inputs, outputs, falhas e security boundaries estão em [`docs/02-system-architecture.md`](./docs/02-system-architecture.md). Taxonomia, autoridade, classificação e routing são normativos em [`03-capability-taxonomy.md`](./docs/03-capability-taxonomy.md), [`04-authority-model.md`](./docs/04-authority-model.md), [`05-task-classification.md`](./docs/05-task-classification.md) e [`06-routing-system.md`](./docs/06-routing-system.md).

Um `ExecutionGraph` só é criado quando existe benefício demonstrável de coordenação. O graph possui nodes, edges, owners, budgets, acceptance refs e merge policy. Orchestration, Director e Specialist têm limites em [`07-orchestration-model.md`](./docs/07-orchestration-model.md), [`08-director-model.md`](./docs/08-director-model.md) e [`09-specialist-model.md`](./docs/09-specialist-model.md).

## 5. Capabilities e composição

Todo pacote futuro declara `CapabilityManifest`, `SKILL.md`, provenance, dependencies, conflicts, contracts, gates, stops, evals e security policy. O padrão do pacote e do `SKILL.md` está em [`10-capability-package-standard.md`](./docs/10-capability-package-standard.md) e [`11-skill-md-standard.md`](./docs/11-skill-md-standard.md). A composição usa handoffs tipados; exemplos e anti-patterns estão em [`12-composition-contracts.md`](./docs/12-composition-contracts.md), [`35-routing-examples.md`](./docs/35-routing-examples.md) e [`36-anti-patterns.md`](./docs/36-anti-patterns.md).

Os 12 contratos conceituais em [`docs/contracts/`](./docs/contracts/) são a fonte de forma para `TaskProfile`, `RouteDecision`, `ExecutionGraph`, `CapabilityManifest`, `CapabilityInvocation`, `ArtifactRecord`, `EvidenceRecord`, `VerificationReport`, `CritiqueReport`, `QualityReport`, `TelemetryEvent` e `RunSummary`. São pseudocode documental, não schemas instalados.

## 6. Proof, AAA e segurança

Cada claim requerido aponta para procedure e evidence fresca. Verification lista passed, failed, not-run, unknown e limitations; review tem independence level; assurance aplica quality bar, residual risk e stop conditions. Os detalhes estão em [`docs/13-verification-system.md`](./docs/13-verification-system.md), [`14-assurance-system.md`](./docs/14-assurance-system.md), [`15-stop-conditions.md`](./docs/15-stop-conditions.md), [`21-quality-model.md`](./docs/21-quality-model.md) e [`22-aaa-definition.md`](./docs/22-aaa-definition.md).

AAA bands:

- `AAA_VERIFIED`: required gates passed, evidence fresh, no critical/high blocker aberto, critique/assurance adequado e limitações aceitas pela autoridade.
- `AAA_CANDIDATE`: bar majoritariamente coberto, mas falta evidence/independência/freshness ou decisão autorizada.
- `ACCEPTABLE`: objetivo pode ser entregue com risco/limitação explícitos, mas não satisfaz AAA.
- `BLOCKED`/`FAILED`: não há base para entrega como concluída.

Security é transversal: least privilege, input validation, secret hygiene, data classification, redaction, provenance e audit são gates, conforme [`23-security-model.md`](./docs/23-security-model.md). Falha e degradação preservam trabalho e honestidade, conforme [`24-failure-model.md`](./docs/24-failure-model.md) e [`25-degradation-model.md`](./docs/25-degradation-model.md).

## 7. Estado, records e observabilidade

Task status, gate status, verification status e evidence freshness são dimensões separadas. O state machine proposto e o modelo de artifacts estão em [`27-state-model.md`](./docs/27-state-model.md) e [`26-artifact-model.md`](./docs/26-artifact-model.md). `RunSummary` não reduz estados incompatíveis a um único `PASS`.

Telemetry é append-only e privacy-aware; `CAPABILITY_LOADED` é factual somente quando observado pelo host ou adapter. Logs, traces, métricas e replay estão em [`18-telemetry.md`](./docs/18-telemetry.md) e [`19-observability.md`](./docs/19-observability.md). Métrica causal exige baseline/control group ou declaração honesta de que existe apenas proxy.

## 8. Codex-native boundary

O design toma como fatos públicos apenas as superfícies verificadas: instruções em `AGENTS.md`, Skills e seus recursos, subagents, tools/MCP e camadas de configuração. Matching exato, precedência de duplicatas, host load, compaction interna, schemas futuros e disponibilidade universal são `UNKNOWN`/`PROPOSED` até observação controlada. Ver [`docs/30-design-director-integration.md`](./docs/30-design-director-integration.md), ADR-009 e o registro de fontes em [`docs/README.md`](./docs/README.md).

O `design-director` é golden reference visual: direction, medium choice, source of truth, rendered inspection, critic e bounded iteration são reutilizados como padrões transferíveis. Seu escopo visual não é convertido em Director universal; integração explícita está em [`docs/30-design-director-integration.md`](./docs/30-design-director-integration.md).

## 9. Modernização e entrega futura

Modernização ocorre em waves com inspect current/upstream, boundary nativo, manifest, contracts, gates, deterministic checks, known-bad evals, benchmark, promotion/rejection e drift monitor. O programa está em [`docs/33-skill-modernization-program.md`](./docs/33-skill-modernization-program.md) e o template em [`docs/34-modernization-template.md`](./docs/34-modernization-template.md). Directors de engineering, design, game, research e outros são roadmap, não capacidades instaladas; ver [`docs/28-domain-directors.md`](./docs/28-domain-directors.md)–[`docs/32-research-director.md`](./docs/32-research-director.md).

A estrutura alvo, roadmap e prioridades estão em [`docs/37-repository-structure.md`](./docs/37-repository-structure.md), [`docs/38-implementation-roadmap.md`](./docs/38-implementation-roadmap.md) e [`docs/39-priority-matrix.md`](./docs/39-priority-matrix.md). O registry inicial deve começar por contracts, authority, classification, router, verification e stops — não por uma proliferação de agentes.

## 10. Acceptance da fase documental

Esta fase está pronta somente quando: os 45 documentos numerados/constitucionais pedidos existem; os 10 ADRs, 12 diagramas e 12 contracts existem e estão indexados; há pelo menos 30 exemplos de routing; terminology/link/reference checks passam; nenhuma implementação runtime ou alteração de Skill/config global foi feita; audit local e review adversarial registram gaps, limitações, riscos e readiness.

A decisão final está em [`docs/44-final-documentation-report.md`](./docs/44-final-documentation-report.md). A auditoria e a revisão são [`docs/42-documentation-audit.md`](./docs/42-documentation-audit.md) e [`docs/43-independent-review.md`](./docs/43-independent-review.md). Nenhuma dessas páginas prova que o futuro harness já existe.
