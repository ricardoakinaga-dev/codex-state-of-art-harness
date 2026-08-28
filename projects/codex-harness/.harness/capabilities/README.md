# Capabilities locais

Cada capability adicionada ao projeto deve ter um diretório próprio nesta
árvore, com manifesto, owner, provenance, compatibilidade, dependências e
escopo explícitos. O manifest também registra `origin`, `precedence`,
`source_hash`, `installation_scope` e `project_scope`; conflitos de ID/versão
entre origens são bloqueados até resolução explícita. A Fase 1 não instala nem
substitui Skills e não fornece capabilities executáveis.
