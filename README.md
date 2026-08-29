# Codex State of Art Harness

Este repositório separa explicitamente arquitetura, projetos, capabilities e
referências. Nenhum projeto ou capability deve compartilhar um diretório
genérico de runtime.

## Estrutura

- [`architecture/`](./architecture/) — `HARNESS-SPEC.md`, documentação, ADRs,
  contratos e diagramas arquiteturais.
- [`projects/codex-harness/`](./projects/codex-harness/) — projeto isolado da
  implementação verificada da Fase 1, do kernel local congelado da Fase 2,
  das extensões read-only/host da Fase 3–4 e do piloto bounded de composição
  visual da Fase 5, com código, testes, configuração, estado e evidências próprios.
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
`PROPOSED`; as Fases 1–4 estão verificadas dentro de seus limites declarados;
a Fase 5 foi fechada como piloto bounded de composição visual em
`PASS_WITH_LIMITATIONS`/suporte A. O pacote não prova composição geral,
produção ou runtime completo do Codex.

Para trabalhar no kernel, entre em [`projects/codex-harness/`](./projects/codex-harness/)
e use o `pyproject.toml` local. A Fase 3 pode inspecionar e indexar metadados
do host em modo somente leitura, mas não instala, executa ou modifica Skills,
subagents, MCP, shell, rede, credenciais ou produção.
