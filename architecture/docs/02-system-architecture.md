# 02 — System Architecture

## Status

**Target:** `PROPOSED`
**Current runtime:** não implementado neste workspace.
**Authority:** [`04-authority-model.md`](./04-authority-model.md) e [`12-composition-contracts.md`](./12-composition-contracts.md).

## Modelo de alto nível

```text
USER GOAL
   ↓
RUNTIME ADAPTER → CONTEXT MANAGER → POLICY ENGINE
   ↓                    ↓                 ↓
INTENT + SCALE + RISK CLASSIFIERS ← CAPABILITY REGISTRY
   ↓
DOMAIN ROUTER → DOMAIN DIRECTOR
   ↓                    ↓
ORCHESTRATOR?       TASK GRAPH / QUALITY BAR
   ↓                    ↓
SPECIALISTS ↔ TOOLS / PROVIDERS
   ↓
INTEGRATOR → VERIFICATION → DOMAIN REVIEW → ASSURANCE / GAUNTLET
   ↓
DELIVERY → ARTIFACT / EVIDENCE / STATE / TELEMETRY
   ↓
EVALS → LEARNING INPUT (não autoaltera produção)
```

O fluxo é uma decomposição de responsabilidades, não uma obrigação de executar todas as caixas. O router deve retornar explicitamente `activate`, `optional` e `do_not_activate`.

## Critério para uma nova caixa

Um componente só pode existir se resolve ao menos um destes problemas:

1. decisão distinta que muda rota ou segurança;
2. fronteira de falha/ownership que precisa ser isolada;
3. contrato reutilizado por três ou mais consumers;
4. evidência determinística que não deve depender de reasoning;
5. estado/telemetria que precisa sobreviver a uma sessão;
6. variação de domínio/provider que tem lifecycle próprio.

Se for apenas uma regra local, deve ser regra no documento/registry, não um serviço ou agente novo. [`36-anti-patterns.md`](./36-anti-patterns.md) e [`37-repository-structure.md`](./37-repository-structure.md) aplicam essa parcimônia.

## Component contract matrix

Todos os componentes da tabela são propostos. “Authority” significa a decisão que o componente pode produzir, não prioridade sobre instruções do Codex.

| Componente | Purpose / problem solved | Input → output | Authority | Dependencies | Failure modes | Observability | Security boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Runtime Adapter | Traduzir o host Codex para interfaces estáveis sem assumir internals | host request/state → `TaskEnvelope` | pode declarar capacidades disponíveis; não redefine policy | Codex host, tool surface | schema drift, unavailable surface | adapter/version/tool inventory | host permissions, sandbox, network |
| Intent Classifier | Separar objetivo, deliverable e constraints | user goal → intent + confidence | classifica; não autoriza ação material | input, context | intent ambiguity, prompt injection | classification trace, alternatives | input sanitization, untrusted text |
| Complexity Classifier | Escolher profundidade proporcional | context + change surface → scale | propõe scale; Director pode revisar com evidência | repository/context | under/overclassification | scale evidence | não eleva privilege |
| Risk Classifier | Capturar security/data/user/irreversibility | task profile → risk vector | escalates, never downgrades unilaterally | policy, boundaries | hidden high risk, unknown | risk trace, blockers | trust boundaries, human stops |
| Domain Router | Mapear profile para capabilities | `TaskProfile` + registry → `RouteDecision` | decide composição mínima e gates | registry, policy | collision, miss, unavailable | route trace | cannot bypass safety |
| Capability Registry | Fonte de manifests, versões, conflitos e evidence | manifests → query/resolve | governança de registro; não executa | package store, validator | duplicate, stale, invalid contract | registry audit | provenance, package trust |
| Director Layer | Transformar goal em strategy, bar e graph | goal/profile/context → plan/bar/graph | define strategy e acceptance | router, registry | god director, invented scope | decision records | respects external authority |
| Orchestrator Layer | Executar DAG/delegação condicionais | graph + budgets → task results | schedules/cancels/retries within graph | agent host, artifact store | fan-out, deadlock, partial failure | task/retry/cost traces | per-task permissions |
| Specialist Layer | Resolver uma fronteira de domínio | scoped handoff → artifact/evidence | decide dentro do scope; escalates conflicts | tools, references | scope creep, unsupported claims | invocation/handoff | least privilege, input/output boundary |
| Tool/Provider Layer | Produzir observações ou ações reais | invocation → tool result | tool runtime owns execution result | MCP/native/provider | timeout, auth, schema drift | tool trace, provenance | network/secret/provider permissions |
| Integrator | Unificar outputs sem apagar conflitos | artifacts → integrated candidate | reconciles interfaces; cannot invent pass | graph, contracts | merge conflict, contradictory outputs | merge log, unresolved list | cross-boundary data handling |
| Verification Layer | Responder o que foi testado e observado | candidate + criteria → report | autoridade sobre evidência executada | tests, runtime, artifacts | stale/not-run/invalid harness | verification ledger | test isolation, redaction |
| Reviewer Layer | Desafiar domínio e integração | artifact + bar → findings | pode rejeitar dentro do review scope | verifier output, artifact | bias, shallow review | review record, independence | read-only by default |
| Assurance Layer | Aplicar gauntlet e stop criteria | reports + bar + budget → quality decision | blocks delivery for unresolved required gaps | reviewer, policy, telemetry | loop hell, false confidence | quality/retry/stop trace | no privilege escalation |
| Eval System | Medir regressões e causalidade | scenarios + runs → eval results | owns oracle/eval status, not live delivery | fixtures, runners, graders | gaming, invalid control | eval run/score | fixture isolation, PII minimization |
| Telemetry System | Emitir eventos correlacionáveis | lifecycle signals → events | owns event schema/retention | state/artifact/tool hooks | dropped/out-of-order events | event health, cost | redact secrets, access control |
| Context Manager | Carregar/compactar contexto útil | profile + references → context pack | selects disclosure; cannot omit required evidence | registry, state | context overflow, stale summary | load/eviction/token proxy | sensitive context ACL |
| Policy Engine | Aplicar safety, authority, budgets e gates | decision + policy → allow/block/condition | can block; cannot authorize prohibited external action | external policy, human authority | policy conflict, stale approval | policy decision/audit | strongest control boundary |
| State Store | Persistir execution state e recovery pointer | transitions → durable state | state consistency; no product verdict | storage, ledgers | corruption, drift, stale pointer | state/recovery events | integrity, encryption, retention |
| Artifact Registry | Indexar outputs e provenance | artifacts → query lineage | artifact identity/status, not quality | filesystem/object store | orphan, overwrite, provenance loss | artifact lifecycle | path/object ACL, no unsafe overwrite |
| Evidence Store | Preservar observações verificáveis | procedures/results → evidence records | freshness/trace binding | verification, telemetry | stale, missing, tampered | evidence health | redaction, immutability/audit |

## Decision and activation matrix

A matriz acima descreve o contrato operacional; esta segunda matriz fecha as perguntas de design que impedem a arquitetura de virar uma coleção de caixas: por que o host/native não basta, qual o custo incremental e quando não ativar. Os custos são estimativas qualitativas até existir benchmark; `context`, `latency` e `maintenance` são medidos separadamente em implementação.

| Componente | Por que uma camada adicional pode ser necessária além do native Codex | Custo incremental esperado | Não ativar quando |
| --- | --- | --- | --- |
| Runtime Adapter | Host fornece superfícies, mas um contrato estável precisa separar fato observado de adapter/proposta sem copiar internals. | baixo por run; médio de manutenção | a tarefa usa diretamente uma superfície nativa já observada e não precisa de record interoperável |
| Intent Classifier | O host recebe texto, mas não emite necessariamente um profile persistente de goal, deliverable, non-goals e ambiguity. | baixo de contexto/latência | objetivo já está estruturado e a inspeção não revela ambiguidade material |
| Complexity Classifier | Native execution não define a profundidade proporcional ao change surface. | baixo | profile fresco já tem complexity/evidence válidos; nunca como planner pesado |
| Risk Classifier | Safety nativa é autoridade superior, mas vetor de data/user/irreversibility é específico da tarefa e precisa de trace. | baixo; pode aumentar discovery | sem side effect material e sem boundary de dados/segurança além de uma checagem focal |
| Domain Router | Skills/tools podem ser encontradas, mas uma decisão mínima com inclusões, exclusões, conflitos e fallback precisa de artifact. | baixo a médio | execução direta é claramente suficiente ou registry não está disponível; nesse caso registrar limitation |
| Capability Registry | Filesystem/catalog enumera pacotes, mas não resolve versão, provenance, conflicts, eval e promotion state como contrato. | médio de manutenção | typo/lookup local de uma sessão sem composição ou lifecycle |
| Director Layer | General model pode planejar, mas domain bar, ownership e acceptance persistentes exigem um boundary explícito em trabalho material. | alto de contexto; médio de coordenação | TRIVIAL/SMALL sem ambiguidade, uma boundary e um único acceptance check |
| Orchestrator Layer | Subagents/tools nativos executam, mas graph, dependency, retry, cancellation e partial merge não devem ficar implícitos. | alto de latência/contexto e coordination | não há duas lanes independentes, side effects isoláveis ou ganho líquido esperado |
| Specialist Layer | Modelo geral pode cobrir o domínio, porém uma boundary específica precisa de handoff, tool policy e output contract próprios. | médio por capability carregada | não há sinal de domínio, input contract ou tool realmente disponível |
| Tool/Provider Layer | É a boundary que observa/age de fato; uma Skill não substitui execução native/MCP/provider. | depende do tool, rede e credencial | provider não é necessário, não está autorizado ou não há equivalência de fallback |
| Integrator | Fan-in nativo não garante merge semântico, lineage e preservação de conflito entre lanes. | médio de contexto/coordenação | há apenas um artifact acoplado e nenhum cross-boundary merge |
| Verification Layer | Test runner pode retornar exit code, mas claims, coverage, freshness, not-run e unknown precisam ser ligados a acceptance. | baixo a médio por gate | nenhum claim material existe além de um focused static check; ainda registrar o check aplicável |
| Reviewer Layer | Self-check é útil, mas não provê crítica read-only independente ou domain challenge contra bar. | médio de contexto/latência | tarefa trivial ou mudança sem risco/qualidade material; não usar para preencher um ritual |
| Assurance Layer | Verification e review não controlam sozinhos largest-gap, residual risk e bounded stop. | alto; apenas quando o bar justifica | TRIVIAL/SMALL ou não há risco/high-fidelity que requeira challenge |
| Eval System | Uma execução live não é baseline, fixture, oracle ou regressão comparável. | médio de manutenção; custo offline | não há hipótese de mudança de capability/route ou ainda não existe cenário válido |
| Telemetry System | Logs do host podem existir, mas causal route/load/cost/quality e privacy classification exigem event contract próprio. | médio de armazenamento/privacy | evento conteria raw secret/PII desnecessária ou a decisão é one-off sem claim observability |
| Context Manager | O host gerencia contexto, mas progressive disclosure, invalidation e budget por profile são policy da arquitetura. | baixo por tarefa; médio de policy | tarefa é pequena e o contexto já cabe sem pack/references adicionais |
| Policy Engine | Safety/approval nativos não devem ser reimplementados; uma camada proposta só acrescenta gates locais, budgets e audit. | médio de manutenção | apenas duplicaria uma decisão superior do host ou criaria uma autoridade paralela |
| State Store | Conversa mantém contexto, mas recovery multi-turn/partial e histórico imutável precisam de pointer/ledger durável. | médio de I/O/retention | execução é efêmera, reversível e termina em uma resposta sem artifact material |
| Artifact Registry | Filesystem guarda bytes, mas não necessariamente lineage, digest, supersession, access class e lifecycle. | médio de I/O/retention | output é descartável e não participa de claim, merge ou recuperação |
| Evidence Store | Tool/test output existe, mas evidence atual requer procedure, freshness, provenance, limitation e vínculo com claim. | médio de storage/metadata | não há claim verificável além de um resultado explicitamente não-material |

## Invariantes arquiteturais

- O caminho direto é válido e mensurável.
- Nenhuma capability altera a autoridade externa do host.
- Router, Director, Orchestrator, Verification e Assurance têm outputs diferentes.
- Um provider fornece dados/ações; uma capability fornece workflow/policy.
- Todo output material tem `status`, `confidence`, `provenance` e `evidence_refs` quando fizer claim.
- Toda repetição tem orçamento e reason-to-continue.
- Nenhuma etapa transforma `UNKNOWN`, `NOT_RUN`, `BLOCKED` ou `PREDICTION` em `PASS`.
- Cada componente declara quando não deve rodar.

## Boundaries e deployment futuro

O design não exige microservices. A primeira implementação deve preferir módulos no mesmo processo quando a fronteira não exigir isolamento. A separação lógica é obrigatória; separação física só é justificada por segurança, escala, ownership, falha ou lifecycle. Uma implementação futura pode começar por `router + registry + state/evidence` e manter specialists como invocações de Skill/native tools.

## Escala de implantação proposta

| Escala | Forma mínima | Forma não permitida por default |
| --- | --- | --- |
| local/single-run | módulos + arquivos de artefato | daemon/serviços extras sem necessidade |
| multi-turn | state/evidence append-only + recovery | memória não rastreável |
| multi-agent | task graph + per-agent scope + integrator | writers concorrentes no mesmo recurso |
| team/CI | registry versionado + evals + policy | promoção automática sem review |
| high-risk | isolação, autoridade humana, audit trail, recovery | ação irreversível sem aprovação |

## Tracing mínimo

`task_id` é estável no objetivo; `run_id` identifica uma execução; `invocation_id` identifica uma chamada de capability; `artifact_id` identifica um output; `evidence_id` identifica uma observação. Esses IDs atravessam [`18-telemetry.md`](./18-telemetry.md), [`26-artifact-model.md`](./26-artifact-model.md) e `contracts/`.
