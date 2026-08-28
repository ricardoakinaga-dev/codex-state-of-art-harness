# 18 — Telemetry

## Propósito

Telemetry torna routing, load, tool use, cost, retry, quality e learning observáveis. É proposta: o audit local afirma que host-load trace não está exposto; portanto `CAPABILITY_LOADED` abaixo só será factual após instrumentação futura.

## Eventos

```text
TASK_RECEIVED
TASK_CLASSIFIED
ROUTE_SELECTED
CAPABILITY_SELECTED
CAPABILITY_LOADED
TOOL_CALLED
TOOL_RESULT
RETRY
VALIDATION_RUN
VALIDATION_FAIL
CRITIQUE_RUN
GAUNTLET_PASS
GAUNTLET_FAIL
DELIVERY
```

Eventos adicionais podem existir, mas não devem duplicar `RunSummary`/state sem owner. Todos carregam:

```yaml
telemetry_event:
  event_id: EVT-0001
  timestamp: 2026-08-28T12:00:00Z
  task_id: TASK-1
  run_id: RUN-1
  capability: backend-engineering
  event_type: TOOL_CALLED
  reason: "public boundary verification"
  input_size: 1200
  output_size: 400
  token_estimate: 1600
  duration_ms: 820
  tool: test-runner
  result: PASS
  severity: null
  confidence: HIGH
  artifact_refs: [ART-3]
  privacy_class: INTERNAL
```

## Causal requirements

Para atribuir efeito a Skill, registrar pelo menos: control group/route, selected vs loaded, body/reference versions, tool calls, context input, output, quality score, latency, cost, task family e blind grade. Self-report de nome não satisfaz `CAPABILITY_LOADED`.

## Privacy e segurança

Não logar secrets, tokens, raw `.env`, private prompts sensíveis ou PII desnecessária. Hash/digest e categorias substituem conteúdo quando possível. Access control e retention são definidos por policy. Telemetry de provider pode ter termos/limites próprios; provenance e consentimento precisam ser respeitados.

## Métricas

- route precision/recall e overactivation/miss;
- loaded context/token estimate e custo real quando disponível;
- tool success/failure, latency e fallback;
- retry count, no-progress e stop causes;
- evidence coverage/freshness;
- critic finding rate por severity;
- quality por task family/profile;
- simple-task latency e unnecessary activation rate.

Métricas são instrumentos para perguntas, não score universal. Sempre declarar baseline, workload, sample e blind spots.

## Integrity

Eventos são append-only, correlacionados e ordenados por timestamp/event sequence; out-of-order é preservado e sinalizado. Event loss cria limitation e pode bloquear causal claim. `DELIVERY` nunca é inferido só porque não houve error.
