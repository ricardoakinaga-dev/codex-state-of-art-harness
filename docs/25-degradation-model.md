# 25 — Degradation Model

## Princípio

Quando uma peça falha, o Harness preserva trabalho não afetado, reduz somente claims dependentes e torna o bloqueio legível. Degradação é uma rota explícita, não sucesso fabricado.

## Níveis

| Nível | Quando | Output |
| --- | --- | --- |
| `FULL` | dependencies/evidence/gates completos | artifact + report completo |
| `PARTIAL` | lanes independentes concluídas, dependência não crítica falhou | artifact parcial + affected scope + next action |
| `FALLBACK` | ferramenta/capability substituída por rota autorizada | result + equivalence limitation + provenance |
| `BLOCKED` | required boundary/authority/evidence missing | no completion claim; blocker + request |
| `FAILED` | bounded attempts esgotadas e artifact não atende | failure report + root cause/unknowns |

## Regras

- preservar artifacts e evidence válidos;
- marcar claims afetados `UNKNOWN`, `NOT_RUN` ou `BLOCKED`;
- comunicar efeito no outcome original;
- não downgrade de risco sem nova evidence;
- continuar tasks não dependentes;
- escolher fallback com owner e quality bar compatível;
- revalidar após provider/tool/environment voltar;
- nunca chamar degraded output de AAA/secure/production-ready.

## Exemplo

Sem Browser, uma UI pode receber static contract/semantic inspection, mas render/responsive/interaction ficam `NOT RUN`. O output pode ser um handoff `PARTIAL`; o router não deve apagar design QA da lista.

## Fallback matrix

```text
native tool unavailable
  → authorized provider / serial procedure
  → evidence status FALLBACK + compare limitations
provider unavailable
  → source current alternative / stop research
  → freshness/provenance explicitly changed
subagent unavailable
  → single-agent separated review
  → independence limitation recorded
required specialist absent
  → direct route with minimum verification
  → specialized quality claim blocked
```

## Delivery

Delivery parcial exige escopo, accepted limitations e autoridade do user. Se o artifact parcial for útil sem o missing boundary, pode ser entregue como tal; se o missing gate é central, estado global permanece `BLOCKED`.
