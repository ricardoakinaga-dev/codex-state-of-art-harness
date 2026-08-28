# 10 — Capability Package Standard

**Natureza:** `NORMATIVE` para qualquer capability futura do Harness.
**Status de implementação:** nenhum pacote futuro é criado nesta fase.

## Estrutura

```text
capability-name/
├── SKILL.md
├── references/
├── agents/
├── scripts/
├── evals/
├── benchmarks/
├── rubrics/
├── templates/
├── examples/
└── assets/
```

As pastas são opcionais por necessidade. `SKILL.md` é obrigatório. A presença de uma pasta não é prova de qualidade.

## Regras por diretório

| Diretório | Necessário quando | Conteúdo permitido | Não deve conter |
| --- | --- | --- | --- |
| `SKILL.md` | sempre | identity, trigger, workflow, contracts, gates, stops | manual enciclopédico ou código runtime |
| `references/` | conhecimento extenso/condicional | policies, schemas, domain guides, source notes | regras conflitantes não linkadas |
| `agents/` | existem briefings/metadata específicos da capability | role packets, UI metadata compatível com host | promessa de custom agent runtime sem suporte |
| `scripts/` | check determinístico reduz julgamento | validators, parsers, benchmark runners | harness principal ou bypass de segurança |
| `evals/` | capability material/reutilizável | scenarios, fixtures refs, oracles, known-bad | testes que só validam texto esperado |
| `benchmarks/` | comparação de qualidade/custo/latência/fidelidade | versão do benchmark e workload | threshold ajustado para passar |
| `rubrics/` | julgamento qualitativo é relevante | anchors, severity, scoring rules | score sem evidence |
| `templates/` | output repetido precisa forma estável | handoffs, reports, briefs | dados de produção ou secrets |
| `examples/` | onboarding/composição precisa exemplos | examples pequenos e rotulados | exemplo como garantia de runtime |
| `assets/` | output precisa material reutilizável | referências, fixtures, imagens licenciadas | cópia de identidade sem provenance |

## Manifest mínimo

O Registry deve conseguir responder: nome único, versão, descrição de ativação, tipo primário, owner, scope, status, source/provenance, dependencies, conflicts, tools, context cost estimate, security boundary, quality gates, eval/benchmark refs, compatibility e deprecation. Ver [`contracts/CapabilityManifest.json.md`](./contracts/CapabilityManifest.json.md).

## Provenance e versionamento

Cada pacote registra origem, licença quando aplicável, snapshot/upstream, data de inspeção, mudanças locais e confidence. “Upstream mais novo” é dado de idade, não evidência de superioridade. Promoção exige A/B ou benchmark equivalente e review.

## Instalação e distribuição

Esta especificação não escolhe uma instalação global. Um futuro pacote deve declarar se é standalone Skill, plugin, MCP companion ou capability interna. O host Codex continua autoridade para descoberta, confiança, configuração e permissões. O package standard não modifica `.codex/config.toml`, `$CODEX_HOME`, Skills instaladas ou roots por conta própria.

## Segurança do pacote

- scripts devem ser safe-by-default, bounded, redacted e sem external mutation por padrão;
- references nunca devem embutir credenciais;
- assets têm provenance/licensing;
- dependências obrigatórias têm preflight e fallback;
- manifestos inválidos não são roteáveis;
- capability sem `do_not_activate` e stop conditions não pode ser promovida a implicit.

## Promotion states

`EXPERIMENTAL → CANDIDATE → VERIFIED → STABLE → DEPRECATED/REJECTED`. Promotion não é feita por presença em disco. `VERIFIED` exige eval/benchmark corrente, package validator, review independente proporcional e ausência de Critical finding.

## Compatibilidade

Compatibilidade de host, tool, model, runtime, provider e versão deve ser explícita. `agents/openai.yaml`, quando presente, é metadata de UI/invocação conforme o host; não deve ser tratado como definição universal de subagent. O padrão preserva a separação pública entre Skill workflow e MCP tool/action documentada pelo OpenAI.
