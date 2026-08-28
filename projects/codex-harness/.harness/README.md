# `.harness/` — project-owned kernel boundary

Este diretório pertence exclusivamente a este projeto. Ele contém configuração,
manifests, estado, evidência, telemetria, evals e cache locais da Fase 1.

O kernel lê dados aqui como entradas não confiáveis e nunca escreve em Skills
instaladas, `~/.codex`, servidores MCP ou no submódulo `skill-audit`.

Não há executor nesta fase: o layout não habilita `harness run`.
