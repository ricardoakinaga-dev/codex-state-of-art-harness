# 23 — Security Model

## Objetivo

O Harness deve aumentar disciplina sem virar uma nova superfície de privilégio. Security é contextual à boundary; uma capability que manipula auth, secrets, input, network, files, plugins, MCP ou production tem controles adicionais.

## Least privilege

- cada task recebe somente ferramentas e arquivos necessários;
- specialist não herda credenciais de outra lane;
- reviewer é read-only por default;
- provider token é scoped, nunca escrito em prompt/artifact/log;
- scripts operam em fixtures/temporary roots e recusam broad/destructive targets;
- registry/package só carrega fonte confiável e versão conhecida;
- permissions/sandbox/approval são do host e não podem ser ampliados por Skill.

## Boundaries

| Boundary | Controle mínimo |
| --- | --- |
| input/user text | classify untrusted content, prompt-injection awareness, validate scope |
| filesystem/repo | exact path, instruction scope, no broad destructive operation |
| shell/tool | allowlist/capability, timeout, output redaction, audit event |
| network/provider | explicit availability/auth, TLS/endpoint policy, rate/cost limits |
| MCP/plugin | trust/permissions, server instructions, tool schema/provenance |
| subagent | minimal brief, isolated ownership, no secrets/PII, read-only review |
| data | fixture isolation, retention/deletion policy, sensitivity tags |
| delivery | human approval for production/irreversible/high risk |

## Secrets

Nunca embutir API keys, passwords, tokens, raw `.env`, private keys ou PII desnecessária em Skill, prompt, telemetry, report, contract fixture ou agent brief. Usar variável/secret manager autorizado e referenciar somente o nome. Se secret aparecer, parar a exposição, redigir e escalar rotação pela autoridade correta; esta fase não faz rotação.

## Unsafe operations

Destructive production action, uncertain data deletion, credential handling, irreversible migration, security-sensitive decision, material financial/regulatory impact e residual high/critical risk são human-stop triggers. Inspeção/preparação segura pode continuar sem executar a ação.

## Provenance

Artefato, input, provider, package, reference, model/tool e output devem ter origem/status. `UNKNOWN` é preservado. Não tratar nome de repositório/owner como prova de autoria/licença; o audit local separa provenance, fork e authorship.

## Audit events

Registrar permission decision, denied tool, secret redaction, provider auth, package load, override, human approval, security finding e recovery. Audit trail é append-only e access-controlled.

## Security review gate

Security reviewer verifica actor/resource/action, validation/encoding/path, authz, session/token, secret/log exposure, rate/replay/idempotence, dependency/config e auditability conforme boundary. Um scanner sem threat model não prova segurança ampla.
