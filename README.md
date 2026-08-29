# Codex State of Art Harness

Este repositório separa explicitamente arquitetura, projetos, capabilities e
referências. Nenhum projeto ou capability deve compartilhar um diretório
genérico de runtime.

## Estrutura

- [`architecture/`](./architecture/) — `HARNESS-SPEC.md`, documentação, ADRs,
  contratos e diagramas arquiteturais.
- [`projects/codex-harness/`](./projects/codex-harness/) — projeto isolado da
  implementação verificada da Fase 1, do kernel local congelado da Fase 2 e
  da extensão read-only de integração de host da Fase 3, com código, testes,
  configuração, estado e evidências próprios.
- [`capabilities/`](./capabilities/) — reservado para futuros pacotes de
  capability, cada um em seu próprio diretório.
- [`references/skill-audit/`](./references/skill-audit/) — submódulo de auditoria
  usado como referência somente leitura; seu conteúdo não pertence ao runtime.

## Isolamento obrigatório

Todo projeto futuro recebe um diretório dedicado em `projects/`. Toda capability
futura recebe seu próprio diretório em `capabilities/` ou dentro do limite
explicitamente definido pelo projeto. Não misture `src`, testes, estado,
configuração ou dependências de unidades diferentes.

Status explícito: a arquitetura do sistema em `architecture/` continua
`PROPOSED`; a Fase 1 está `IMPLEMENTED/VERIFIED`; a Fase 2 está congelada como
`PASS_WITH_LIMITATIONS` dentro do kernel local; a Fase 3 é o alvo atual para
integração read-only do host e ainda não prova o runtime completo do Codex.

Para trabalhar no kernel, entre em [`projects/codex-harness/`](./projects/codex-harness/)
e use o `pyproject.toml` local. A Fase 3 pode inspecionar e indexar metadados
do host em modo somente leitura, mas não instala, executa ou modifica Skills,
subagents, MCP, shell, rede, credenciais ou produção.
