# `.harness/` — project-owned kernel boundary

Este diretório pertence exclusivamente a este projeto. Ele contém configuração,
manifests, estado, evidência, telemetria, evals e cache locais das Fases 1 e 2.

O kernel lê dados aqui como entradas não confiáveis e nunca escreve em Skills
instaladas, `~/.codex`, servidores MCP ou no submódulo `skill-audit`.

Na Fase 2, o layout habilita somente `harness run` com providers determinísticos
locais registrados no kernel. Não há execução de Skills, módulos de input,
subagents, MCP, shell, rede ou provider real.
