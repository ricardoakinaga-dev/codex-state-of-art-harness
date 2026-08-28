# 09 — Specialist Model

## Boundary

Specialist é uma capability com profundidade de domínio e superfície limitada. O specialist recebe um handoff fechado, escolhe referências/tools dentro dele, produz artifact e evidence, e entrega ao Integrator/Verification. A especialização existe para aumentar precisão em uma fronteira, não para criar um novo centro de autoridade.

## Specialist contract

```yaml
specialist_contract:
  name: backend-engineering
  type: SPECIALIST
  purpose: "Resolver lógica server-side, persistência e falhas dentro do scope."
  activate_when: [backend boundary, service/API implementation]
  do_not_activate_when: [copy-only, pure visual, no backend surface]
  can_call: [tool/shell, database-inspection, verification]
  can_be_called_by: [engineering-director, orchestrator]
  must_run_before: [integrator]
  must_run_after: [classification, acceptance]
  conflicts_with: [another backend owner on same files]
  inputs: [TaskProfile, handoff, contracts, relevant references]
  outputs: [artifact, evidence, risks, unresolved questions]
  tools: [native shell, project tests]
  security_constraints: [validate inputs, no secrets in outputs]
  escalation: [auth/data/architecture/authority conflict]
  quality_gates: [local correctness, boundary contract, regression]
```

## No-activation rules

- Não ativar por menção de uma tecnologia que não está no deliverable.
- Não ativar se a própria capability está ausente ou dependência obrigatória não foi verificada.
- Não ativar dois specialists para o mesmo ownership sem contrato de peer review.
- Não ativar specialist de framework só porque o nome do framework aparece em texto não técnico.
- Não ativar security specialist para qualquer palavra “safe”; deve existir trust boundary, auth, secrets, input, abuse ou explicit request.
- Não ativar media specialist quando o output é UI code/text.

## Ferramentas determinísticas

O specialist deve preferir parser, linter, test runner, browser, schema validator, benchmark ou provider adequado quando o resultado pode ser verificado. Reasoning descreve decisões; não substitui uma observação que a ferramenta pode produzir.

## Deliverables

Um handoff mínimo contém:

- o que mudou/foi produzido;
- arquivos/artefatos exatos;
- decision/root-cause evidence;
- comandos/procedures executados e resultados;
- limitações e status `PASS/PARTIAL/FAIL/BLOCKED/NOT_RUN`;
- dependências resolvidas e não resolvidas;
- risco residual e escalation;
- próxima boundary e owner.

## Escalonamento

Escalar quando surgir:

- mudança fora do ownership;
- requirement/architecture conflict;
- security/data/irreversibility;
- provider unavailable ou output não verificável;
- acceptance insuficiente;
- falha repetida sem nova hipótese.

Escalonamento não é silêncio e não é licença para ampliar scope.

## Exemplos futuros

`backend-engineering`, `frontend-engineering`, `api-engineering`, `security-engineering`, `database-engineering`, `performance-engineering` e `gameplay-engineering` são candidatos. Cada um deve provar boundary e value por eval antes de promoção. O registry não deve registrar apenas nomes: precisa de contracts, tests, dependencies, provenance e promotion status.

## Specialist review

Um specialist pode fazer self-check, mas trabalho material exige `PEER`/`INDEPENDENT` reviewer quando disponível. A ausência de reviewer é limitation, não aprovação automática. O design-director usa a mesma regra para visual work.
