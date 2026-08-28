# ADR-003 — Orquestração somente quando há ganho demonstrável

**Status:** `PROPOSED` · **Data:** 2026-08-28 · **Escopo:** execução

## Contexto

Paralelismo e fan-in podem reduzir tempo em trabalho independente, mas introduzem coordenação, custo de contexto, conflitos e risco de falsa completude.

## Decisão

O Orchestrator executa apenas um `ExecutionGraph` autorizado. Fan-out requer independência demonstrável; todo lane tem owner, input/output contract, budget, retry policy e gate. Integrator preserva partials e conflitos. A execução degrada honestamente para single-agent quando a DAG não paga seu overhead.

## Alternativas consideradas

- Fan-out fixo por complexidade: simples, porém incentiva overactivation.
- Paralelizar toda etapa independente aparente: ignora side effects e merge.
- Não orquestrar: perde valor em mudanças multi-boundary.

## Consequências

Mais campos precisam ser registrados antes de executar, mas latency, custo e qualidade podem ser comparados por graph. Retries são limitados e nunca escondem falha estrutural.

## Evidência

`docs/07-orchestration-model.md`, `docs/15-stop-conditions.md`, `docs/25-degradation-model.md` e o framework de engenharia aplicado como referência processual.

## Revalidação

Executar benchmark com lane serial versus DAG; exigir ganho líquido de qualidade/latência/custo, não somente mais agentes ativos.
