# 16 — Context Management

## Objetivo

Maximizar reliability por token carregando apenas o contexto que responde à decisão atual. Contexto não é armazenamento de verdade: decisões/requirements/evidence duráveis ficam em artefatos canônicos e são referenciadas por ID/path.

## Progressive disclosure

```text
L0 user goal + constraints
L1 metadata/registry match
L2 SKILL.md kernel
L3 focused references/contracts
L4 target files/tools/artifacts
L5 history/upstream only for named uncertainty
```

Não carregar a árvore inteira, todos os providers ou todos os logs por default. O Director pede expansão quando o profile, risco, domínio ou falha justifica.

## Context budget

Cada run declara budget de input/contexto, max capabilities/kernels, max references, max tool outputs, max retries e compaction checkpoints. O budget é controle de custo e não pode suprimir evidence required. Se necessário, reduzir escopo/latência explicitamente.

O audit usa contagem de palavras como proxy e não como billed-token telemetry. O Harness deve preferir host trace quando disponível e manter proxy marcado como `ESTIMATE`.

## Inheritance

Subagent recebe somente goal local, bar aplicável, rules, owned boundary, dependencies, baseline e required evidence. Não herda logs/rationale irrelevantes. Specialist recebe handoff e links, não um dump do chat. Reviewer não recebe defesa do builder.

## Summarization

Resumo pode compactar logs e resultados, mas deve preservar IDs, status, command/procedure, timestamps, artifact paths, confidence, limitations e next action. Não compactar um `UNKNOWN` em fato nem apagar falhas.

## Evidence compaction

Guardar raw output em artifact quando necessário; no contexto usar digest/path/observed result. Sempre manter o vínculo reversível para inspeção. Um summary stale é invalidado quando artifact/requirement/environment muda.

## Evitar duplicação

- um documento possui a regra; outros linkam;
- `41-glossary.md` possui definição canônica;
- contracts possuem campos; docs explicam uso sem copiar schema inteiro;
- state guarda ponteiros, não transcrições;
- telemetry guarda IDs e metadados, não secrets/raw PII.

## Tarefas grandes

Director faz context slicing por lane. Integrator faz fan-in de outputs. Context Manager detecta explosão quando: número de kernels/references excede budget, repetição de texto cresce sem nova evidence, tool output é maior que o artifact, ou critic não consegue localizar acceptance. A resposta é resumir/particionar/replan, não simplesmente carregar mais.

## Codex boundary

O Harness não afirma thresholds/formatos internos de compaction que a documentação oficial não garante. Configuração global, project trust, AGENTS e host loading permanecem autoridade do Codex; o Harness apenas prepara packs e registra o que foi observado.
