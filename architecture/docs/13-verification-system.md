# 13 — Verification System

## Papel

Verification é a camada autoritativa sobre o que foi executado e observado. Ela não decide sozinha se o produto é bom, nem transforma uma explicação em prova. Seu output responde exatamente:

```text
WHAT WAS CLAIMED?
WHAT WAS TESTED?
WHAT PASSED?
WHAT FAILED?
WHAT WAS NOT RUN?
WHAT REMAINS UNKNOWN?
```

## Contrato de relatório

```yaml
verification_report:
  report_id: VER-0001
  task_id: TASK-0001
  artifact_refs: [ART-0001]
  claims:
    - id: CLAIM-1
      text: "endpoint rejects missing account_id"
      status: PASS
      evidence_refs: [EVID-11]
  procedures:
    - id: PROC-1
      command_or_procedure: "integration test at API boundary"
      status: EXECUTED
      result: PASS
  passed: [CLAIM-1]
  failed: []
  not_run: ["load test"]
  unknown: ["production latency"]
  limitations: ["isolated fixture; no production traffic"]
  confidence: HIGH
  blockers: []
  recommendation: PASS
```

O schema completo está em [`contracts/VerificationReport.json.md`](./contracts/VerificationReport.json.md). `recommendation` é recomendação de evidência, não autorização de release.

## Evidência válida

Preferência: observação real de boundary → teste determinístico → métrica reproduzível → static inspection vinculada à regra → inspeção manual estruturada → explicação. `PREDICTION` e `EXPLANATION` não satisfazem claim requerido. `NOT_RUN`, stale e missing evidence permanecem explícitos.

Cada record deve conter procedure, status de execução, environment, result, artifact/evidence, observed_at, freshness, limitations e confidence. Command PASS exige exit status 0; observações podem não ter exit status, mas ainda precisam de procedimento executado e observação concreta.

## Gates

- correctness/acceptance;
- error and recovery behavior;
- relevant regression;
- security/data/authorization quando expostos;
- contract/schema/compatibility;
- observability/operability quando in scope;
- documentation/traceability;
- visual render/interaction para high-fidelity.

O conjunto é selecionado pelo profile; não é uma lista universal. Uma mudança documental como esta verifica links, cobertura, consistência, fonte e ausência de implementation leakage.

## Freshness e invalidacão

Evidence passa a stale quando muda o artifact, requirement, environment, dependency, tool result, gate ou qualquer evento que invalide a observação. Uma nova versão do relatório aponta para records novos; não reescreve PASS antigo.

## Verificação versus review

Verification executa procedimentos e relata facts. Reviewer compara facts contra bar e procura gaps. Assurance desafia o sistema e decide se deve continuar/stop. O mesmo agente pode fazer passes separados quando não há subagents, mas o nível é `SEPARATED_SELF`, nunca `INDEPENDENT`.

## Ausência de evidência

O relatório sempre lista `not_run` e `unknown`. Se o browser, provider, host-load trace, runtime, fixture ou credential não existe, declarar `BLOCKED`/`NOT_RUN` no escopo afetado. Não reduzir a conclusão para esconder a lacuna.

## Completion claim

`completed` só pode ser usado quando acceptance required passou, artifact está integrado e limitações estão registradas. `secure`, `production-ready` e `AAA` exigem gates próprios e authority adequada; verification sozinho não concede esses rótulos.
