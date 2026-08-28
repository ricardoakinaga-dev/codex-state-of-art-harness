# 01 — Problem Statement

## Framing

**Problema observado:** o ambiente Codex tem uma coleção útil de aproximadamente 40 capabilities, mas a superfície de ativação e composição é suficientemente plana para que responsabilidades de controle, domínio, provider, qualidade e assurance concorram por linguagem semelhante. Isso aumenta a probabilidade de custo desnecessário, rotas incompletas, autoridade contraditória e confiança maior que a evidência.

**Evidência:** o audit congelado em 2026-08-28 encontrou 41 caminhos de `SKILL.md`, 40 nomes declarados, 39 nomes visíveis e uma duplicação byte-identical de `engineering-framework`. O veredicto do audit é `CONDITIONAL PASS`, não prova causal de melhoria universal. Ver [`skill-audit/reports/00-executive-summary.md`](../skill-audit/reports/00-executive-summary.md) e [`01-skill-inventory.md`](../skill-audit/reports/01-skill-inventory.md).

## Sintomas e limites do estado atual

### Flat skill topology

Não há uma camada única e explícita, observável no audit, que conecte escala/risco → capability mínima → owner → evidência → stop. Control plane, engineering, quality, assurance, research, media e providers aparecem como vizinhos. A classificação funcional já sugere uma separação, mas classificação estática não é routing runtime: [`02-functional-classification.md`](../skill-audit/reports/02-functional-classification.md).

### Overactivation

O probe de cinco casos observou composição possivelmente excessiva em S2, S3 e S5. S2 incluiu framework, TDD, security e E2E numa tarefa grande; S3 incluiu docs lookup, API, backend, TDD e security; S5 incluiu gauntlet, orchestration e security sem que toda essa superfície estivesse necessariamente justificada. O audit mede um self-report do modelo, não o host-load real: [`07-benchmark-results.md`](../skill-audit/reports/07-benchmark-results.md).

### Underactivation

O mesmo probe observou que S3 omitiu a rota explícita de verification-loop e que S5 teve recall baixo. A ausência de uma capability pode ser correta, mas atualmente não existe uma decisão estruturada que diferencie “não precisava” de “foi esquecida”. O routing precisa registrar `do_not_activate` e `required_quality_gates`, não apenas nomes escolhidos.

### Ambiguity de authority

`engineering-framework`, `orchestrate`, `verification-loop` e `gauntlet-loop` falam de complexidade, execução, review ou quality. O audit propõe uma hierarquia de responsabilidade, mas a precedência exata entre os dois caminhos de `engineering-framework` e o host-load permanece `UNKNOWN`: [`13-authority-model.md`](../skill-audit/reports/13-authority-model.md).

### Routing collision

O audit identifica colisões entre framework/orchestrate; framework/TDD; verification/gauntlet; eval-harness/verification; research/provider; graphic/image/media; content/crosspost; e coding-standards/especialistas. Similaridade lexical é apenas proxy e não autoriza merge: [`04-overlap-analysis.md`](../skill-audit/reports/04-overlap-analysis.md) e [`12-instruction-collisions.md`](../skill-audit/reports/12-instruction-collisions.md).

### Context pollution

O corpus visível tem aproximadamente 36.943 palavras e o catálogo projetado cerca de 13.040 caracteres, acima do proxy de 8.000 caracteres documentado no baseline local. Isso é um indicador de risco; não prova que todos os corpos são carregados a cada turno. O custo por rota também é apenas proxy de palavras, não billed-token telemetry: [`11-context-pollution.md`](../skill-audit/reports/11-context-pollution.md).

### Duplicated process

Verification, TDD, E2E, engineering framework e gauntlet podem repetir “testar”, “revisar” e “qualidade” sem um contrato que diga quem produz o quê. O risco não é ter várias ferramentas; é gerar vários verdicts incompatíveis ou carregar processos universais.

### Portability debt

O audit encontrou referências a Claude hooks/settings, `.claude/evals`, providers/configs externos e capabilities opcionais ausentes (`brand-voice`, `videodb`, `continuous-learning`, `liquid-glass-design`, `connections-optimizer`). Isso deve produzir route `FALLBACK` ou `BLOCKED` com `reason_code=UNAVAILABLE`; se o trabalho continuar com escopo afetado, o lifecycle/artifact pode ser `PARTIAL`. Nunca há sucesso implícito: [`03-static-audit.md`](../skill-audit/reports/03-static-audit.md) e [`05-dependency-graph.md`](../skill-audit/reports/05-dependency-graph.md).

### Lack of causal telemetry

O host não expôs trace de seleção/load de Skill. A rota self-reported não prova qual body foi carregado nem seu custo. Sem `TASK_RECEIVED → CAPABILITY_LOADED → TOOL_CALLED → VALIDATION → DELIVERY`, não se pode atribuir ganho ou regressão a uma capability. Essa é a maior lacuna de avaliação: [`06-benchmark-methodology.md`](../skill-audit/reports/06-benchmark-methodology.md).

### Lack of deterministic verification

O `engineering-framework` tem evidência executável forte sobre a integridade do próprio pacote (doctor 42 PASS/1 WARN/0 FAIL, evals 6 PASS/1 WARN/0 FAIL, 216 testes PASS), mas isso não prova melhoria universal do modelo ou causalidade de routing. Outras capabilities combinam texto, proxies e observação limitada. O Harness precisa separar validade do pacote, execução atual e efeito causal.

### Generic output problem

Uma capability que só adiciona prosa tende a produzir “AI slop”: respostas plausíveis, genéricas, sem especificidade de domínio, sem estados de erro, sem ferramenta adequada e sem prova. O design-director oferece um teste útil: se remover nome/logo ainda parece criado para qualquer produto, falta especificidade. Essa heurística precisa ser adaptada por domínio e nunca substituir evidence.

### Premature completion

Claims como `completed`, `fixed`, `verified`, `secure`, `production-ready` ou `AAA` podem aparecer sem procedimento executado, evidência atual, revisão separada ou limitation. O Harness precisa tornar ausência de evidência visível e bloquear somente o que a evidência realmente não suporta.

### Tool underutilization

O Codex já possui superfícies nativas para shell/patch, web, browser, MCP, image generation e subagents conforme o host. Skill deve escolher e governar a ferramenta; não deve fingir que uma instrução textual substitui um boundary real. A documentação oficial de Skills e MCP é a fonte pública para essa distinção; ver links no [`README.md`](./README.md).

### Missing specialist direction

Especialistas atuais são úteis, mas a coleção não mostra, como contrato comum, `CAN_CALL`, `CAN_BE_CALLED_BY`, `MUST_RUN_BEFORE`, `CONFLICTS_WITH`, output, tool prerequisites e escalation. A ausência de contrato transforma composição em associação lexical.

## Exemplos derivados da auditoria

| Caso observado | Sintoma | Causa estrutural provável | Resposta arquitetural |
| --- | --- | --- | --- |
| S1 “typo/local trivial” | rota direta funciona, mas sem contrato formal de bypass | no-skill route não é artefato de primeira classe | classificar trivial e registrar capabilities desativadas |
| S2 tarefa grande | 4 Skills, custo proxy 5.278 palavras | TDD/E2E/security/framework não têm gate comum | Director define graph; specialists são overlays; TDD/E2E condicionais |
| S3 endpoint médio | docs/API/backend/TDD/security, sem verification explícita | boundary de provider, implementação e prova se mistura | route output exige verification e justifica docs lookup só com incerteza atual |
| S5 revisão iterativa | gauntlet + orchestrate + security, precision proxy 0,3 | “grande” é tratado como “paralelizar” e “assurance” | orchestration gate + trust-boundary gate + gauntlet apenas por bar |
| duplicate framework | duas cópias idênticas | root precedence não observável | policy canonical + hash validator + migração futura controlada |
| refs ausentes | brand-voice/videodb/etc. referenciados sem path | dependência opcional sem status | preflight com `reason_code=UNAVAILABLE` e degradação explícita |

## Hipóteses testáveis

- H1: routing por escala/risco reduz overactivation sem reduzir recall em famílias fixas.
- H2: separação Director/Orchestrator/Verification/Gauntlet reduz verdicts contraditórios.
- H3: progressive disclosure reduz custo de contexto e mantém qualidade nos mesmos fixtures.
- H4: tool/provider preflight reduz falhas silenciosas e falsos claims de sucesso.
- H5: critique independente captura gaps que self-review não captura.

Cada hipótese exige baseline, workload, controle, métrica e oráculo em [`20-eval-framework.md`](./20-eval-framework.md). Até então, as hipóteses são `PROPOSED`, não resultados.

## Não-problemas

- Ter 40 nomes não é, por si só, defeito.
- Similaridade lexical não é prova de duplicação semântica.
- Provider-specific Skill não é inútil só porque existe uma ferramenta nativa.
- Um loop não é ruim por ser iterativo; é ruim quando não tem progresso, orçamento ou critério de saída.
- Um score alto não compensa falha crítica, evidência ausente ou autoridade inválida.

## Resultado desejado

Para cada tarefa, o sistema deve produzir um profile, uma decisão de rota, um grafo opcional, contratos de handoff, artefatos, evidência, crítica e motivo de entrega/parada. Uma tarefa simples deve continuar simples; uma tarefa crítica deve ganhar profundidade sem que isso seja inferido apenas da palavra “grande”.
