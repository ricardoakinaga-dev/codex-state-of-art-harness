# 19 — Observability

## Camadas

- **Logs:** eventos estruturados, error class, decision, owner, scope e redaction.
- **Traces:** span por task, route, capability, tool, retry, validation, review e delivery.
- **Metrics:** throughput, latency, context/cost, activation, evidence, quality, stop/failure.
- **Audit trail:** alterações de policy, manifest, authority, gate, override, evidence e provenance.
- **Dashboards:** vistas por run, domínio, task class, capability e trend.
- **Debug mode:** detalhes adicionais em ambiente seguro, sem desabilitar controle.
- **Replay:** reproduzir input/fixtures/config/version/route com side effects simulados ou isolados.

## Visualizações essenciais

| View | Responde |
| --- | --- |
| routing trace | por que capability foi/ não foi ativada? |
| capability trace | qual kernel/reference/version realmente carregou? |
| tool trace | qual chamada, provider, latency, result e fallback? |
| cost trace | tokens/contexto/calls/latency por lane e por route |
| retry trace | qual failure, hipótese e progress em cada attempt? |
| quality trace | bar, evidence, findings, score, residual risk e stop |

## Correlation

`task_id → run_id → span_id → invocation_id → tool_call_id → artifact_id/evidence_id` forma a cadeia. Logs sem correlation não provam causalidade. Artifact path precisa ser acompanhado de digest/provenance para evitar nome plausível apontando para output diferente.

## Error classes

Categorizar routing, contract, permission, tool, provider, context, validation, critic, integration, loop e security. O dashboard separa error de outcome: um tool `PASS` não garante quality `PASS`.

## Alertas/thresholds

Alertas são definidos por quality profile, não hardcoded universalmente. Exemplos: activation rate acima do budget; required evidence stale; retry loop; dropped telemetry; Critical finding; provider auth failures; cost/latency tail.

## Replay e determinismo

Replay deve usar fixture versionada, clock/ordering/cache controlados e side effects bloqueados. Um replay não substitui runtime real quando essa é a boundary do claim. Diferenças de host/model/provider ficam no report.

## Operação segura

Debug não deve expor secrets ou habilitar unsafe operation. Retenção, acesso, exportação e redaction são auditáveis. Observability failure gera `UNKNOWN`/`BLOCKED` sobre os claims que dependem dela, não um zero-error dashboard artificial.
