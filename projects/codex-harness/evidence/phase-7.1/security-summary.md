# Security summary

Status: `PASS_WITH_LIMITATIONS`.

Passaram os testes de path traversal/symlink, JSON estrito e duplicate keys,
deserialização, redaction/secret logging, authorization/ownership, credential
boundary, prompt injection, tool escalation, stale evidence e artifact
substitution. O scan textual de source/tests/scripts/pilot não encontrou
material de credencial real; os matches são nomes de campos e fixtures
sintéticas deliberadas.

Comandos estáticos passados: `ruff check src tests scripts pilots`,
`ruff format --check src tests scripts pilots`, `mypy --strict src` e
`compileall`. `pip-audit`, Bandit, Semgrep e Trivy não estão disponíveis no
ambiente; não há `package.json` nem dependência npm neste projeto. Isso impede
um claim de aprovação de segurança ou produção.
