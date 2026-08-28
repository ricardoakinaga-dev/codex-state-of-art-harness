# 15 — Stop Conditions

## Princípio

Cada loop define antes de começar as condições de continuar, parar com sucesso, parar bloqueado e pedir autoridade. “Continue até perfeito” vira um objetivo de melhoria, não uma permissão para gastar sem limite ou ocultar falha.

## Condições

| Condição | Detecção | Ação | Autoridade |
| --- | --- | --- | --- |
| `MAX_ITERATIONS` | attempts atingem budget definido | parar, preservar último artifact e reportar gap | Orchestrator/Assurance |
| `NO_PROGRESS` | duas rodadas não mudam criterion/evidence | reexaminar hipótese, replan ou escalar | Director/Assurance |
| `REPEATED_FAILURE` | mesma falha com mesma causa/entrada | não retry cego; novo diagnóstico ou block | owner + Assurance |
| `OSCILLATION` | fix de A quebra B e retorno repete | congelar versões, revisar root cause/contract | Integrator/Director |
| `BUDGET_EXHAUSTION` | tokens, tempo, calls, custo ou context budget acabou | entrega parcial honesta ou block | user/project authority |
| `MISSING_TOOL` | tool/provider required não disponível | `FALLBACK` permitido ou `BLOCKED` com `reason_code=UNAVAILABLE` | Router/Policy |
| `BLOCKED_DEPENDENCY` | prerequisite absent/stale/failed | bloquear dependents, continuar independentes | Orchestrator |
| `HUMAN_OVERRIDE` | user/authority pede stop ou aceita trade-off | registrar override/limitation/revalidation | autoridade humana |
| `ACCEPTABLE_RESIDUAL_RISK` | todos required pass e remaining gaps marginal/non-blocking | concluir com score/confidence/scope | Assurance + delivery authority |

## Limites obrigatórios

Não é permitido: retry de side effect não idempotente, contornar permission/safety, baixar threshold para passar, converter `BLOCKED` em `PARTIAL PASS` sem scope, ou tratar ausência de critic como independent.

## Quem pode parar

- Tool/Provider para sua operação em erro de segurança/permissão/timeout.
- Specialist para boundary local e escalonamento.
- Orchestrator para dependency, ownership, budget ou cancellation.
- Verification para evidence invalid/stale.
- Assurance para required gap, no progress, oscillation ou residual risk.
- User/human authority sempre pode interromper; override não reclassifica o resultado.

Nenhuma camada interna pode autorizar ação proibida pelo host ou aceitar high/critical risk sem autoridade.

## Stop report

```yaml
stop:
  condition: NO_PROGRESS
  observed_after: 2
  last_progress: EVID-44
  unresolved_gaps: [GAP-7]
  impact: "schema contradiction remains"
  action: REPLAN
  owner: director
  confidence: HIGH
  next_revalidation: "new contract review"
```

## Condições de sucesso

Sucesso requer gates required PASS, artifact integrado, evidence atual, critic proporcional e residual risk aceito pela autoridade correta. `MAX_ITERATIONS` ou `BUDGET_EXHAUSTION` nunca são sucesso por si só.
