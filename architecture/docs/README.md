# Codex Capability Harness — documentação de referência

Esta é a especificação documental do futuro `Codex Capability Harness`. Ela define uma arquitetura adaptativa para composição de capacidades, mas não implementa runtime, router, registry, telemetry pipeline ou qualquer outro componente executável. Tudo que descreve o alvo é `PROPOSED` até uma fase futura de implementação e validação.

## Como ler

1. Comece por [`HARNESS-SPEC.md`](../HARNESS-SPEC.md), a constituição resumida.
2. Use [`00-vision.md`](./00-vision.md) e [`01-problem-statement.md`](./01-problem-statement.md) para entender o porquê.
3. Leia [`02-system-architecture.md`](./02-system-architecture.md), [`04-authority-model.md`](./04-authority-model.md) e [`06-routing-system.md`](./06-routing-system.md) para o núcleo de controle.
4. Consulte [`12-composition-contracts.md`](./12-composition-contracts.md), [`13-verification-system.md`](./13-verification-system.md), [`15-stop-conditions.md`](./15-stop-conditions.md) e `contracts/` para contratos operacionais.
5. Use [`41-glossary.md`](./41-glossary.md) como vocabulário canônico. Se outro documento divergir, abra uma correção registrada em [`42-documentation-audit.md`](./42-documentation-audit.md); não crie um segundo vocabulário.

## Mapa completo

### VISION

- [`00-vision.md`](./00-vision.md) — visão, escopo, antiobjetivos e definição operacional de Triple-A.
- [`01-problem-statement.md`](./01-problem-statement.md) — problema observado e limitações do stack atual.

### ARCHITECTURE

- [`02-system-architecture.md`](./02-system-architecture.md) — componentes, fronteiras e fluxo de alto nível.
- [`03-capability-taxonomy.md`](./03-capability-taxonomy.md) — tipos formais de capability.
- [`04-authority-model.md`](./04-authority-model.md) — autoridade externa, interna e poder de bloqueio.
- [`05-task-classification.md`](./05-task-classification.md) — classificação multidimensional e classes.
- [`06-routing-system.md`](./06-routing-system.md) — router, precedência, fallback e prevenção de overactivation.
- [`07-orchestration-model.md`](./07-orchestration-model.md) — DAG, lanes, retries, cancelamento e merge.
- [`08-director-model.md`](./08-director-model.md) — Domain Director.
- [`09-specialist-model.md`](./09-specialist-model.md) — especialistas, contratos e escalonamento.
- [`10-capability-package-standard.md`](./10-capability-package-standard.md) — padrão de pacote.
- [`11-skill-md-standard.md`](./11-skill-md-standard.md) — padrão normativo de `SKILL.md`.
- [`12-composition-contracts.md`](./12-composition-contracts.md) — contratos de composição.

### EXECUTION AND PROOF

- [`13-verification-system.md`](./13-verification-system.md) — claims, evidência e limitações.
- [`14-assurance-system.md`](./14-assurance-system.md) — verification, review e gauntlet.
- [`15-stop-conditions.md`](./15-stop-conditions.md) — condições de parada e autoridade.
- [`16-context-management.md`](./16-context-management.md) — progressive disclosure e budget de contexto.
- [`17-tool-selection.md`](./17-tool-selection.md) — seleção deliberada de ferramenta/provider.
- [`18-telemetry.md`](./18-telemetry.md) — eventos, campos e causalidade.
- [`19-observability.md`](./19-observability.md) — logs, traces, métricas, replay e dashboards.
- [`20-eval-framework.md`](./20-eval-framework.md) — evals permanentes e oráculos.
- [`21-quality-model.md`](./21-quality-model.md) — dimensões e perfis de qualidade.
- [`22-aaa-definition.md`](./22-aaa-definition.md) — bandas AAA, bloqueios e evidência.

### SECURITY AND FAILURE

- [`23-security-model.md`](./23-security-model.md) — least privilege, sandbox, secrets e provenance.
- [`24-failure-model.md`](./24-failure-model.md) — falhas, detecção, recuperação e escalonamento.
- [`25-degradation-model.md`](./25-degradation-model.md) — degradação honesta e preservação de trabalho.
- [`26-artifact-model.md`](./26-artifact-model.md) — artefatos e proveniência.
- [`27-state-model.md`](./27-state-model.md) — estados e transições da execução.

### CAPABILITIES AND EVOLUTION

- [`28-domain-directors.md`](./28-domain-directors.md) — roadmap de Directors.
- [`29-engineering-director.md`](./29-engineering-director.md) — integração futura do engineering-framework.
- [`30-design-director-integration.md`](./30-design-director-integration.md) — golden reference visual.
- [`31-game-director.md`](./31-game-director.md) — game-director proposto.
- [`32-research-director.md`](./32-research-director.md) — pesquisa, providers e síntese.
- [`33-skill-modernization-program.md`](./33-skill-modernization-program.md) — waves de modernização.
- [`34-modernization-template.md`](./34-modernization-template.md) — template de promoção/rejeição.
- [`35-routing-examples.md`](./35-routing-examples.md) — 30+ casos de roteamento.
- [`36-anti-patterns.md`](./36-anti-patterns.md) — modos de falha arquiteturais.

### GOVERNANCE AND DELIVERY

- [`37-repository-structure.md`](./37-repository-structure.md) — estrutura futura justificada.
- [`38-implementation-roadmap.md`](./38-implementation-roadmap.md) — fases e critérios de saída.
- [`39-priority-matrix.md`](./39-priority-matrix.md) — P0–P3.
- [`40-risk-register.md`](./40-risk-register.md) — riscos e controles.
- [`41-glossary.md`](./41-glossary.md) — termos oficiais.
- [`42-documentation-audit.md`](./42-documentation-audit.md) — gate e findings da própria documentação.
- [`43-independent-review.md`](./43-independent-review.md) — revisão adversarial separada.
- [`44-final-documentation-report.md`](./44-final-documentation-report.md) — relatório final e readiness.

### ADRs

- [`adr/ADR-001-capability-architecture.md`](./adr/ADR-001-capability-architecture.md)
- [`adr/ADR-002-director-model.md`](./adr/ADR-002-director-model.md)
- [`adr/ADR-003-orchestration-policy.md`](./adr/ADR-003-orchestration-policy.md)
- [`adr/ADR-004-verification-authority.md`](./adr/ADR-004-verification-authority.md)
- [`adr/ADR-005-gauntlet-role.md`](./adr/ADR-005-gauntlet-role.md)
- [`adr/ADR-006-progressive-disclosure.md`](./adr/ADR-006-progressive-disclosure.md)
- [`adr/ADR-007-telemetry.md`](./adr/ADR-007-telemetry.md)
- [`adr/ADR-008-skill-modernization-strategy.md`](./adr/ADR-008-skill-modernization-strategy.md)
- [`adr/ADR-009-codex-native-first.md`](./adr/ADR-009-codex-native-first.md)
- [`adr/ADR-010-design-director-golden-reference.md`](./adr/ADR-010-design-director-golden-reference.md)
- [`adr/ADR-011-python-stdlib-kernel.md`](./adr/ADR-011-python-stdlib-kernel.md) — stack de runtime da Fase 1
- [`adr/ADR-013-phase-4-real-capability-invocation-boundary.md`](./adr/ADR-013-phase-4-real-capability-invocation-boundary.md)
- [`adr/ADR-014-phase-5-design-director-composition-pilot.md`](./adr/ADR-014-phase-5-design-director-composition-pilot.md)

### Implementation

- [`phase-1-quality-bar.md`](../../projects/codex-harness/docs/implementation/phase-1-quality-bar.md) — barra congelada e regras de veredito
- [`phase-5-quality-bar.md`](../../projects/codex-harness/docs/implementation/phase-5-quality-bar.md) — barra congelada para o piloto de composição visual
- [`phase-1-deferred.md`](../../projects/codex-harness/docs/implementation/phase-1-deferred.md) — limites explícitos da Fase 1
- O relatório de implementação da Fase 1 ainda não existe; a implementação foi pausada durante a reorganização estrutural.

### Diagramas Mermaid

Todos os diagramas estão em [`diagrams/`](./diagrams/). O significado semântico e a ordem de autoridade vêm dos documentos normativos, não do desenho isolado:

- [`system-context.mmd`](./diagrams/system-context.mmd) · [`container-architecture.mmd`](./diagrams/container-architecture.mmd) · [`capability-layers.mmd`](./diagrams/capability-layers.mmd)
- [`authority-flow.mmd`](./diagrams/authority-flow.mmd) · [`routing-flow.mmd`](./diagrams/routing-flow.mmd) · [`orchestration-dag.mmd`](./diagrams/orchestration-dag.mmd)
- [`verification-flow.mmd`](./diagrams/verification-flow.mmd) · [`assurance-flow.mmd`](./diagrams/assurance-flow.mmd) · [`state-machine.mmd`](./diagrams/state-machine.mmd)
- [`artifact-flow.mmd`](./diagrams/artifact-flow.mmd) · [`telemetry-flow.mmd`](./diagrams/telemetry-flow.mmd) · [`modernization-flow.mmd`](./diagrams/modernization-flow.mmd)

### Contratos conceituais

Os schemas pseudocode estão em [`contracts/`](./contracts/). Eles são especificações de dados futuras, não código executável:

- [`TaskProfile.json.md`](./contracts/TaskProfile.json.md)
- [`RouteDecision.json.md`](./contracts/RouteDecision.json.md)
- [`ExecutionGraph.json.md`](./contracts/ExecutionGraph.json.md)
- [`CapabilityManifest.json.md`](./contracts/CapabilityManifest.json.md)
- [`CapabilityInvocation.json.md`](./contracts/CapabilityInvocation.json.md)
- [`ArtifactRecord.json.md`](./contracts/ArtifactRecord.json.md)
- [`EvidenceRecord.json.md`](./contracts/EvidenceRecord.json.md)
- [`VerificationReport.json.md`](./contracts/VerificationReport.json.md)
- [`CritiqueReport.json.md`](./contracts/CritiqueReport.json.md)
- [`QualityReport.json.md`](./contracts/QualityReport.json.md)
- [`TelemetryEvent.json.md`](./contracts/TelemetryEvent.json.md)
- [`RunSummary.json.md`](./contracts/RunSummary.json.md)

## Boundary of truth

O audit local é a fonte do estado observado da instalação: [`skill-audit/reports/99-final-audit.md`](../../references/skill-audit/reports/99-final-audit.md). A documentação oficial atual do OpenAI é a fonte para comportamento público do Codex. O alvo desta arquitetura é proposta e não prova de runtime.

Fontes oficiais verificadas em 2026-08-28:

- [Build skills](https://learn.chatgpt.com/docs/build-skills) — Skills são pacotes de workflow com `SKILL.md`, instruções e recursos opcionais.
- [Skills](https://developers.openai.com/plugins/concepts/skills) — separa workflow de Skill e ferramentas/ações de MCP; documenta metadata-first e carregamento sob matching/invocação.
- [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) — cadeia global/projeto, precedência por diretório e merge root-to-CWD.
- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) — delegação paralela, agentes customizados e custo adicional de tokens.
- [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic) — camadas de configuração, confiança de projeto e separação de aprovação/sandbox.
- [MCP](https://learn.chatgpt.com/docs/extend/mcp) — ferramentas/contexto externos, servidores STDIO/HTTP, instruções do servidor e configuração compartilhada.

## Status documental

`architecture/docs/42`, `architecture/docs/43` e `architecture/docs/44` são a autoridade sobre o resultado desta fase. Um documento pode descrever um alvo tecnicamente completo e ainda estar `PROPOSED`; nenhum texto aqui converte uma proposta em capability instalada.
