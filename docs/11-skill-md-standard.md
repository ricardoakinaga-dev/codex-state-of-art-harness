# 11 — SKILL.md Standard

**Norma:** o `SKILL.md` é um router kernel; referências extensas ficam fora dele.

## Estrutura recomendada

```markdown
---
name: capability-name
description: Goal-shaped trigger and non-trigger in one or two sentences.
---

# Identity
# Purpose
# Activate when
# Do not activate when
# Input contract
# Output contract
# Workflow
# Tools
# Deterministic checks
# Quality gates
# Failure modes
# Stop conditions
# Composition
# Degradation
# Evidence
# References
```

Frontmatter deve manter `name` único, lowercase/kebab-case e `description` orientada a user goal/conditions. A descrição não deve despejar o workflow completo.

## Conteúdo obrigatório

| Seção | Pergunta que responde |
| --- | --- |
| Identity | quem é a capability e qual papel primário? |
| Purpose | qual problema ela resolve e qual não resolve? |
| Activate / do not | quais sinais necessários e insuficientes? |
| Input | qual contexto, contrato, limites e permissões? |
| Output | qual artifact/evidence/status? |
| Workflow | quais fases e critérios de skip? |
| Tools | qual meio deliberado e fallback? |
| Deterministic checks | o que deve ser parser/test/validator? |
| Quality gates | critérios required/advisory e evidence |
| Failure/stop | como falha, degrada e encerra? |
| Composition | upstream/downstream/conflicts |
| Evidence | claim, procedure, result, limitations, confidence |
| References | links internos com motivo/when-to-load |

## Limites de disclosure

Não há um limite oficial universal de linhas por `SKILL.md`; os limites abaixo são policy `PROPOSED` do Harness e devem ser medidos contra qualidade:

- target: 150–300 linhas ou até 4.000 palavras;
- revisão obrigatória de split quando ultrapassar 400 linhas/6.000 palavras;
- cada reference deve dizer `Load when` e não repetir regras do kernel;
- scripts/validators devem ser chamados por capability com comando e expected result;
- exemplos grandes vão para `examples/`; schemas para `contracts/` ou `references/`;
- nunca embutir todo upstream ou uma lista completa de providers no kernel.

Esses números são pontos de controle, não prova de eficiência. O benchmark deve verificar se o split reduz contexto sem perder comportamento.

## Progressive disclosure

Layer 1: metadata (name/description) para catalog/routing.
Layer 2: `SKILL.md` completo após match/invocação.
Layer 3: uma ou poucas references necessárias para a decisão atual.
Layer 4: scripts/evals/assets apenas quando o output pede.
Layer 5: fontes históricas/upstream somente se drift/provenance exige.

O Harness não deve assumir detalhes do carregador que o host não documenta. O audit confirma que a documentação pública distingue metadata e corpo de Skill e que o host-load trace local não está exposto.

## Regras de linguagem

- Use “deve” para invariantes normativas e “pode/proposto” para design futuro.
- Distinga `CURRENT`, `PROPOSED`, `INFERRED`, `UNKNOWN`, `NOT RUN`, `BLOCKED`.
- Evite “always” quando o comportamento depende de scale/risk.
- Cada claim de “verified/secure/AAA” aponta para evidence, não para intenção.
- Não declare uma ferramenta disponível só porque aparece em texto; faça preflight.

## Composition block

```yaml
composition:
  can_call: [verification]
  can_be_called_by: [domain-director, router]
  must_run_before: [integrator]
  must_run_after: [classification]
  conflicts_with: [duplicate-owner]
  optional_with: [gauntlet]
  do_not_combine_with: [competing-provider-without-reason]
```

## Quality gate do pacote

Antes de promoção, validar frontmatter, links, dependency refs, no unresolved template markers, known-bad eval, output contract, stop conditions, security boundary, provenance e deterministic checks. A validation não prova que o workflow melhora o modelo; isso pertence ao eval harness.
