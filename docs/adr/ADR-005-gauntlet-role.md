# ADR-005 — Gauntlet como desafio independente e limitado

**Status:** `PROPOSED` · **Data:** 2026-08-28 · **Escopo:** assurance

## Contexto

Uma revisão final precisa procurar o maior gap, não apenas repetir o caminho do builder. Também precisa parar: iteração sem budget vira loop e produz custo sem evidência adicional.

## Decisão

Gauntlet recebe quality bar congelado, artifacts e reports em packet cego quando possível. Ele desafia claims, prioriza o maior risco, classifica findings e recomenda `CONTINUE`, `REPAIR`, `STOP` ou `ESCALATE`. Tem budget de iteração e stop conditions explícitas; não modifica sozinho o artifact nem substitui autoridade externa.

## Alternativas consideradas

- Review textual do mesmo agente: útil como fallback, mas não `INDEPENDENT`.
- Loop até score máximo: não tem critério de parada confiável.
- Gauntlet como gate universal: sobrecarrega tarefas simples.

## Consequências

O processo precisa preservar packet, independence level e limitações. Em ambiente sem subagent, usa-se `SEPARATED_SELF` e a conclusão declara a limitação.

## Evidência

`docs/14-assurance-system.md`, `docs/15-stop-conditions.md`, `docs/22-aaa-definition.md` e o protocolo do skill `gauntlet-loop`.

## Revalidação

Rodar desafio fresh em cada mudança material de arquitetura; parar após a correção do largest meaningful gap e retestar regressões.
