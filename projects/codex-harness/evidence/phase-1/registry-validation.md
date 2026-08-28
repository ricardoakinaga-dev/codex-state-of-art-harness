# Phase 1 registry validation

```text
$ .venv/bin/pytest -q tests/unit/test_registry.py tests/unit/test_routing.py tests/unit/test_authority.py
26 passed
```

O Registry é snapshot imutável e metadata-only. A validação cobre semver,
registro/listagem/busca, resolução de dependências, missing dependency, ciclos,
conflicts, stale/rejected/deprecated, provenance e composição mínima de rota.

Cada manifest também preserva `origin` (`SYSTEM`, `GLOBAL`, `PROJECT`,
`WORKSPACE`, `VENDORED`, `UPSTREAM`), precedência canônica, repository, hash
SHA-256 declarado, installation scope, project scope e derivação opcional.
ID+versão duplicados, inclusive entre origens, exigem resolução explícita e
nunca sofrem shadowing silencioso.

A política numérica congelada é `SYSTEM=500`, `GLOBAL=400`, `WORKSPACE=300`,
`PROJECT=200`, `VENDORED=100` e `UPSTREAM=50`; o mapping é exposto como
somente leitura pelo modelo. A precedência de origem é aplicada antes da
seleção semver, evitando que uma versão upstream mais nova sombreie um pacote
project-local.

A CLI recalcula um hash canônico que cobre o manifesto (com o campo hash
neutralizado) e cada referência local declarada, confirma que `project_scope`
coincide com `project_id`, usa os diretórios definidos no config, resolve
referências de contrato e bloqueia cópias divergentes. A Fase 1 não implementa
loader, instalação ou verificação de conteúdo remoto.
