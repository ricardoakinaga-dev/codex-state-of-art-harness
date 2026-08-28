# 00 — Vision

## Status e escopo de verdade

**Status:** `PROPOSED / DOCUMENTATION-ONLY`
**Escopo:** arquitetura de referência para um futuro Codex Capability Harness.
**Não é:** runtime implementado, plugin instalável, substituição das Skills atuais ou mudança no ambiente Codex.

## Visão

O Codex Capability Harness é uma camada de coordenação e prova que transforma capacidades especializadas, ferramentas nativas, providers e artefatos de qualidade em uma arquitetura adaptativa. A unidade principal não é “um prompt maior”, mas uma capability com fronteira, contrato, contexto progressivo, ferramentas, evidência, avaliação e critérios de parada.

O sistema deve substituir o modelo mental:

```text
Codex + pasta plana de Skills
```

por:

```text
Codex + capability registry + router adaptativo + autoridade explícita
     + specialists + verification + assurance + telemetry + evals
```

O Harness não aumenta magicamente a capacidade do modelo. Ele tenta reduzir decisões mal direcionadas, contexto irrelevante, uso incorreto de ferramentas e conclusão prematura. Essa é uma hipótese testável, não um dogma: qualquer ganho deve ser demonstrado por evals com controle nativo-only, custo, latência e qualidade.

## Problema que queremos resolver

O stack atual possui capacidades reais, mas a topologia observada é plana. Skills de controle, especialistas, providers, verificação e assurance podem competir pela mesma linguagem ampla. O resultado potencial é ativação excessiva, composição incompleta, autoridade ambígua e afirmações fortes sem evidência proporcional. [`01-problem-statement.md`](./01-problem-statement.md) detalha o baseline do audit.

## Objetivos

- Rotear cada tarefa para a menor composição suficiente.
- Escalar profundidade por complexidade, risco, impacto e fidelidade.
- Separar intenção, estratégia, execução, verificação e crítica.
- Tornar autoridade, dependências, conflitos e bloqueios explícitos.
- Preservar capabilities nativas do Codex como autoridade operacional.
- Carregar contexto por progressive disclosure, com custo rastreável.
- Escolher meio, ferramenta e provider deliberadamente.
- Fazer claims somente quando houver evidência atual e proporcional.
- Limitar loops por progresso, risco e orçamento.
- Permitir que novas capabilities sejam promovidas ou rejeitadas por benchmark.
- Deixar uma especificação executável por um engenheiro futuro sem arquitetura escondida.

## Antiobjetivos

- Não criar um agente para cada palavra-chave.
- Não obrigar orchestration, TDD, pesquisa, security review ou gauntlet em tarefas triviais.
- Não duplicar a hierarquia de instruções do Codex.
- Não esconder falhas atrás de `completed`, `fixed`, `secure`, `AAA` ou `production-ready`.
- Não transformar provider em síntese, specialist em director ou verifier em builder.
- Não tratar o design-director como molde universal.
- Não copiar mecanicamente conceitos de Claude Code, Cursor, OpenCode ou outro harness.
- Não substituir uma evidência causal por contagem de linhas, lexical overlap ou self-report do modelo.
- Não alterar, instalar, migrar ou remover Skills como parte desta fase.

## Escopo

Em escopo: taxonomia, autoridade, classificação, routing, orchestration, directors, specialists, pacote de capability, `SKILL.md`, composição, verification, assurance, stop conditions, contexto, ferramentas, telemetria, observabilidade, evals, qualidade, segurança, falhas, degradação, artefatos, estado, directors futuros, modernização, exemplos, ADRs, diagramas, contratos e roadmap.

Fora de escopo: qualquer runtime, daemon, API, banco, plugin, instalação de Skill, alteração de configuração global, migração, deploy, push, integração irreversível ou código de produção.

## Princípios operacionais

1. **Capability over prompt:** workflow + recursos + contratos + prova.
2. **Adaptive depth:** o custo do processo acompanha o risco e o valor da tarefa.
3. **Minimal necessary orchestration:** delegação exige ganho ou lanes independentes demonstráveis.
4. **Clear authority:** cada papel declara decisões permitidas e proibidas.
5. **Evidence before claims:** ausência de evidência é `UNKNOWN`, `NOT RUN` ou `BLOCKED`.
6. **Deterministic when possible:** scripts, schemas, testes e parsers substituem julgamento onde podem.
7. **Builder ≠ approver:** revisão material precisa de contexto separado quando disponível.
8. **Progressive disclosure:** o kernel roteia; references ensinam detalhes sob demanda.
9. **Tool-aware:** o meio é escolhido pelo output e pela fronteira, não por hábito.
10. **Codex-native first:** o Harness compõe o Codex e não inventa fatos sobre seu host.

## State of the Art — definição operacional

Neste projeto, “State of the Art” não significa usar a maior quantidade de agentes, prompts ou providers. Significa uma arquitetura que, em benchmarks reproduzíveis:

- melhora a precisão/recall de routing em relação ao baseline;
- reduz overactivation e custo de contexto sem perder cobertura;
- demonstra comportamento correto por fronteira pública;
- captura ferramentas, falhas, retries, custo e qualidade;
- limita loops e expõe os motivos de parada;
- mantém contratos e responsabilidades verificáveis;
- resiste a tasks adversariais, ambiguidades e providers indisponíveis;
- preserva a rota direta para trabalhos simples;
- revalida claims quando o artefato, requisito ou ambiente muda.

Sem baseline nativo-only e host-load trace, essas propriedades são hipóteses de design. O audit local registra essa limitação em [`skill-audit/reports/07-benchmark-results.md`](../../references/skill-audit/reports/07-benchmark-results.md).

## Triple-A — definição operacional

Triple-A é um gate composto, não um adjetivo. Um resultado só pode ser `AAA_VERIFIED` quando:

1. todos os critérios obrigatórios do perfil da tarefa passam com evidência atual;
2. correctness, segurança, integridade de dados e autorização não têm finding Critical/High não aceito;
3. o domínio teve specialist/reviewer proporcional, sem composição ornamental;
4. ferramentas e providers foram escolhidos e executados corretamente, ou a degradação está explícita;
5. verification separa claims, procedimentos, resultados, limitações e confidence;
6. assurance/critique independente foi executado quando o risco ou a fidelidade exige;
7. iterações foram bounded e pararam por critério observável;
8. o output é específico ao produto/domínio e não generic AI slop;
9. o custo/latência estão dentro do quality profile ou possuem decisão explícita;
10. a proveniência dos artefatos e a rastreabilidade requisito→evidência estão intactas.

As bandas completas estão em [`22-aaa-definition.md`](./22-aaa-definition.md). `AAA_CANDIDATE` é uma hipótese de qualidade; `AAA_VERIFIED` exige gate. Um resultado bloqueado não recebe nota para “compensar” evidência ausente.

## Definição de sucesso desta fase

A fase documental tem sucesso quando um novo engenheiro consegue responder as 20 perguntas do texto-base somente navegando por esta árvore, encontra um contrato para cada fronteira e distingue o que é fato atual, proposta futura, hipótese e desconhecido. Isso será verificado por inventário, link check, inspeção cruzada, contagem de exemplos, revisão adversarial e relatório final — não por extensão do texto.

## Fontes atuais

Os fatos públicos sobre Skills, `AGENTS.md`, subagents, config e MCP usados nesta visão estão ligados em [`README.md`](./README.md). O baseline local e suas limitações permanecem em `references/skill-audit/`; nenhuma fonte local prova que a arquitetura proposta já existe.
