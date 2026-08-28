# 03 — Capability Taxonomy

## Regra de classificação

Uma capability recebe um tipo primário, pode declarar papéis secundários apenas quando não cria autoridade ambígua e deve publicar scope, trigger, dependências, output, conflicts e `do_not_activate`. A taxonomia descreve responsabilidade futura; não classifica automaticamente todas as Skills atuais.

## Tipos normativos

| Tipo | Responsabilidades | Não responsabilidades | Activation rules | Allowed dependencies / authority | Expected output / failure |
| --- | --- | --- | --- | --- | --- |
| `DIRECTOR` | entender goal/contexto, definir strategy, bar, graph, acceptance e integração | executar tudo, self-approve, substituir verification | cross-domain, architecture, material uncertainty ou explicit user ask | router, registry, context, policy; authority de estratégia | decision/plan/bar/graph; ambiguities escalate |
| `ORCHESTRATOR` | executar DAG, ownership, fan-out/fan-in, retry/cancel | inventar requirements, fan-out ornamental, final verdict | ≥2 lanes independentes ou ganho de delegação comprovado | graph, agents, state, telemetry; authority de scheduling | task results/status/stop reason; partial failure explícita |
| `ROUTER` | classificar, escolher mínimo, justificar exclusions e gates | executar, revisar domínio, alterar user intent | sempre como função leve; pode no-skill | classifiers, registry, policy; authority de route proposal | `RouteDecision`; ambiguity fallback |
| `PLANNER` | decompor trabalho em tarefas/ordem e validation | redefinir produto sem autoridade | medium+ ou continuity | Director, contracts, state; authority de plan | ExecPlan/task graph; invalid deps block |
| `SPECIALIST` | resolver boundary de domínio com ferramenta adequada | expandir scope, aprovar quality global, agir fora do tool boundary | domain signal e input contract satisfeito | references/tools/registries; authority local | domain artifact + evidence/handoff; escalate |
| `TOOL` | executar operação determinística/nativa | interpretar objetivo completo, inventar resultado | boundary real exige shell/browser/parser/provider | host permission; authority sobre o resultado observado | raw result/artifact; timeout/auth failure |
| `PROVIDER` | oferecer dados/modelo/serviço externo específico | roteamento universal, síntese sem pedido | explicit/provider-specific ou route-selected | network/auth policy; authority limitada à resposta | provider result + provenance; unavailable/partial |
| `REVIEWER` | comparar artifact com bar, encontrar gap, emitir finding | editar o artifact, sugerir pass sem evidence | material change, domain risk, integration | read-only artifact + criteria; authority de review scope | critique report; bias/insufficient evidence |
| `VALIDATOR` | verificar invariantes determinísticas/schema/link/count | julgar qualidade subjetiva ampla | sempre que parser/script pode distinguir bad/good | artifact/contract; authority sobre check result | validation result; invalid harness is failure |
| `ASSURANCE` | challenger adversarial, severity, stop/continue, residual risk | builder, requirement author, endless loop | high bar/high risk/high fidelity ou explicit gauntlet | verification + review + policy; can block delivery | quality/stop decision; budget/no-progress block |
| `RESEARCHER` | buscar, comparar e citar fontes com freshness | implementar sem route, provider competition | current/niche/uncertain facts | search/provider/native web; authority about source evidence | sourced research; stale/missing source |
| `INTEGRATOR` | merge artifacts/contracts, preserve conflicts, package delivery | apagar dissent, declare unverified pass | multi-lane or cross-boundary | artifacts/state/contracts; authority de assembly | integrated artifact + unresolved list |
| `UTILITY` | small reusable transformation/format/normalization | become hidden director or policy owner | deterministic narrow helper | no broad external authority | deterministic output; fail closed |

## Composição permitida

```text
ROUTER → DIRECTOR? → PLANNER? → ORCHESTRATOR?
                         ↘ SPECIALIST → TOOL/PROVIDER
INTEGRATOR → VALIDATOR/VERIFICATION → REVIEWER → ASSURANCE
RESEARCHER → INTEGRATOR (quando synthesis requerida)
```

O `?` é um gate, não um atalho. `TOOL` e `PROVIDER` não chamam `DIRECTOR`; `REVIEWER` não chama builder para consertar o próprio objeto; `ASSURANCE` não muda a Quality Bar para caber no resultado.

## Activation contract comum

Todo manifest deve responder:

- qual user goal ativa;
- quais sinais são necessários;
- quais sinais não bastam;
- qual input mínimo;
- qual output/artifact;
- quais tools/dependencies são obrigatórios ou opcionais;
- quais capabilities conflitam ou precisam vir antes/depois;
- quais gates são obrigatórios;
- quais falhas degradam, bloqueiam ou escalam;
- qual é o máximo de contexto/tempo/iteracões;
- quem pode revisar e quem pode concluir.

## Regra de especialização

Uma capability deve ser mais específica que seu Director. Se uma capability responde por todo o sistema, todas as tarefas e todos os tipos de qualidade, ela provavelmente é um Director disfarçado (`EVERYTHING-AS-DIRECTOR`). Se só repete um comando nativo, ela deve ser uma Utility/Tool ou desaparecer.

## Relação com Skills atuais

O audit local propõe `engineering-framework` como control/director, `orchestrate` como executor condicional, `verification-loop` como evidence owner, `gauntlet-loop` como assurance e providers como camadas separadas: [`skill-audit/reports/13-authority-model.md`](../../references/skill-audit/reports/13-authority-model.md). A promoção real requer manifest, eval e benchmark; essa classificação não modifica os pacotes instalados.
