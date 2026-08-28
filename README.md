# Codex State of Art Harness

Este repositório separa explicitamente arquitetura, projetos, capabilities e
referências. Nenhum projeto ou capability deve compartilhar um diretório
genérico de runtime.

## Estrutura

- [`architecture/`](./architecture/) — `HARNESS-SPEC.md`, documentação, ADRs,
  contratos e diagramas arquiteturais.
- [`projects/codex-harness/`](./projects/codex-harness/) — projeto isolado da
  implementação de kernel da Fase 1, com código, testes, configuração, estado e
  evidências próprios.
- [`capabilities/`](./capabilities/) — reservado para futuros pacotes de
  capability, cada um em seu próprio diretório.
- [`references/skill-audit/`](./references/skill-audit/) — submódulo de auditoria
  usado como referência somente leitura; seu conteúdo não pertence ao runtime.

## Isolamento obrigatório

Todo projeto futuro recebe um diretório dedicado em `projects/`. Toda capability
futura recebe seu próprio diretório em `capabilities/` ou dentro do limite
explicitamente definido pelo projeto. Não misture `src`, testes, estado,
configuração ou dependências de unidades diferentes.

Para trabalhar no kernel, entre em [`projects/codex-harness/`](./projects/codex-harness/)
e use o `pyproject.toml` local. A implementação bounded da Fase 1 vive somente
nessa fronteira; o runtime de execução, a modernização de Skills e a integração
com Codex permanecem adiados.
