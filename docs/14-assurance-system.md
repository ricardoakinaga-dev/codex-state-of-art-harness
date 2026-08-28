# 14 — Assurance System

## Separação de camadas

| Camada | Pergunta | Output | Pode editar? | Pode bloquear? |
| --- | --- | --- | --- | --- |
| Verification | o que foi executado/observado? | claims/evidence/report | não o objeto, por default | por evidência ausente ou falha |
| Domain Review | o resultado é adequado ao domínio? | findings/critique | read-only | dentro do scope |
| Security Review | trust boundaries e abuse cases estão cobertos? | security findings | read-only | security blockers |
| Integration Review | as partes combinam sem drift? | integration findings | read-only | incompatibilidade |
| Gauntlet | qual o maior gap contra o bar e devemos continuar? | assurance/stop report | read-only critic | required gap/loop risk |
| Evals | o padrão regressou em fixtures fixos? | eval result/trend | não live artifact | no-go para promoção |

## Gauntlet

O gauntlet é adversarial, bounded, evidence-aware, severity-aware e independente quando relevante. O loop é:

```text
GOAL → BAR → DECOMPOSE → BUILD → RUN → INSPECT → CRITIQUE
     → SCORE → FIX → RETEST → REPEAT → FINAL CRITIC → STOP
```

Para documentação, `BUILD` significa escrever os documentos solicitados; não significa implementar o harness. Critic recebe goal, bar, artefatos, comandos e limitações, mas não rationale do builder nem score esperado.

## Independence

`SELF` é diagnóstico; `SEPARATED_SELF` é uma checagem temporal com rationale oculto; `PEER` é outro especialista com contexto parcial; `INDEPENDENT` é critic fresco, read-only, blind packet e sem producer overlap. O report deve registrar o nível real.

## Severity e priorização

1. Critical: segurança, autoridade, dados, correctness, false claim ou documentação que inviabiliza implementação.
2. High: boundary faltante, contradição material, contrato inválido, regressão ou route que perde tarefas importantes.
3. Medium: risco de manutenção/custo, cobertura incompleta não bloqueante.
4. Low/polish: clareza ou ergonomia residual.

O maior gap é escolhido por impacto × probabilidade × gap, sem deixar score médio cancelar gate obrigatório.

## Review-agent

Um review-agent pode ser capability interna explícita. Ele não é sinônimo de gauntlet: faz julgamento fresh sobre um scope, enquanto gauntlet controla sequência, orçamento e parada. Se um review-agent está oculto ou explicit-only no host, o registry deve marcar essa disponibilidade como observada/unknown, não presumida.

## Stop do assurance

Assurance para quando gates obrigatórios passam e o residual risk é aceitável, ou quando stop condition é atingida, dependency/authority bloqueia ou ganhos restantes são marginais. Não há loop infinito e não há “mais agentes” como métrica de qualidade.

## Auditoria

Todo report registra bar version, input artifacts, critic identity/independence, procedure, findings por ID, confidence, missing evidence, stop reason e next action. Um finding `ACCEPTED` exige autoridade e residual risk; nunca é apagado.
