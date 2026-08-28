# 41 — Glossary

Este é o vocabulário canônico. Os termos em inglês são identifiers de contratos; a explicação em português é normativa para esta documentação.

| Termo | Definição oficial do projeto |
| --- | --- |
| `AAA` | designation de qualidade que só pode ser atribuída dentro de um profile e gate com evidence; nunca marketing |
| `Artifact` | output identificável com producer, status, provenance, dependencies, confidence e evidence refs |
| `Assurance` | camada que desafia qualidade, severity, residual risk e stop; não é execução |
| `Authority` | poder limitado de decidir/bloquear dentro de uma boundary; não sobrescreve instruções externas |
| `Capability` | unidade composta de workflow, conhecimento, ferramentas, contratos e prova; pode incluir Skill/resources |
| `Capability Registry` | catálogo versionado de manifests, owners, dependencies, conflicts, provenance e promotion state |
| `Claim` | afirmação verificável sobre goal/artifact/quality; exige evidence proporcional |
| `Confidence` | grau de segurança da conclusão (`HIGH`, `MEDIUM`, `LOW`), separado de status/evidence |
| `Context Pack` | conjunto mínimo de goal, profile, constraints, artifacts, decisions, unknowns e next action para uma decisão |
| `Critic` | reviewer read-only que procura maior gap contra bar; não é builder |
| `Degradation` | redução explícita de escopo/evidence quando uma capability/tool/dependency falha |
| `Director` | owner de strategy, quality bar, acceptance e composition de um domínio |
| `Evidence` | observação/procedimento/artefato atual que suporta ou limita um claim |
| `Evidence Store` | armazenamento de records de evidência, freshness, provenance e vínculo com task |
| `Eval` | execução controlada de cenário com fixture, expected, oracle e known-bad |
| `Fallback` | rota alternativa autorizada após falha, com equivalence/limitation registrada |
| `Gauntlet` | loop adversarial e bounded que seleciona gap, exige fix/retest e decide stop |
| `Gate` | condição formal de lifecycle/delivery; required failure bloqueia |
| `Handoff` | pacote de contexto/contrato entregue entre owners |
| `High-fidelity` | tarefa em que correspondência visual/behavioral precisa de evidência extensa e critic |
| `Integrator` | owner de merge semântico de outputs, contracts e provenance; não inventa sucesso |
| `Lane` | unidade de trabalho independente dentro de um DAG |
| `Native-Codex first` | preferir capability/tool nativa; Skill adiciona workflow/policy sem duplicar mecanismo |
| `No-skill route` | decisão explícita de executar diretamente sem carregar capability |
| `Orchestrator` | executor de graph, lanes, retries e cancellation; não owner de requirements/final quality |
| `Overactivation` | capabilities carregadas/ativadas além do mínimo justificado |
| `Provider` | serviço/fonte/modelo externo específico que produz dados/ações; não synthesis universal |
| `Progressive disclosure` | carregar metadata, kernel, references, scripts e history somente conforme a decisão exige |
| `Quality Bar` | critérios frozen com target, evidence, priority, required e validade |
| `Route Decision` | artifact que lista activate, optional, do-not-activate, gates, budget e fallback |
| `Scope` | limite de objetivo, arquivos/boundaries, behavior, risco e authority de uma task |
| `Specialist` | capability de domínio com ownership local e escalation explícito |
| `Stop condition` | regra observável para encerrar sucesso, falha, bloqueio, orçamento ou replan |
| `Telemetry` | eventos correlacionados sobre lifecycle, route, load, tool, cost, retry e quality |
| `Tool` | mecanismo de execução/observação (shell, browser, parser, MCP, provider API etc.) |
| `Underactivation` | ausência de capability/gate necessária ao profile/acceptance |
| `Verification` | camada que registra o que foi claim/testado/passou/falhou/não rodou/unknown |
| `Visual ledger` | variante de evidence ledger para viewport/state/region/render visual |
| `Unknown` | fato/risco/availability/evidence ainda não estabelecido; não pode ser silently PASS |

## Termos proibidos sem qualificação

“production-ready”, “secure”, “verified”, “fixed”, “high quality”, “AAA”, “state of the art” e “works” devem apontar para scope, gate, artifact, procedure, status, confidence e limitation. Sem isso, são claims inválidos.

## Status não intercambiáveis

`IMPLEMENTED`, `VERIFIED`, `PASS`, `PASSED`, `DELIVERED`, `RELEASE_READY` e `AAA_VERIFIED` são diferentes. Use [`27-state-model.md`](./27-state-model.md), [`13-verification-system.md`](./13-verification-system.md) e [`22-aaa-definition.md`](./22-aaa-definition.md) conforme a pergunta.
