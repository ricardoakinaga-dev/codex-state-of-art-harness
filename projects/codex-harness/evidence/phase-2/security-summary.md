# Security summary

Controles verificados:

- `ProjectBoundary` rejeita absoluto, traversal, NUL, symlink de arquivo e
  symlink em diretórios intermediários; atomic writes não seguem output link;
- registry/provider admission rejeita origem não-PROJECT, modos fora da
  allowlist e características de segurança insuficientes;
- parser rejeita `eval`/pickle/import dinâmico, duplicate keys, non-finite JSON,
  profundidade/tamanho excessivos e unknown contract fields;
- authority é obrigatória antes de resolução/chamada;
- output digest, artifact lineage, freshness e evidence links são rechecados;
- telemetry redacts secrets e limita payload/event count;
- erros externos são normalizados sem expor conteúdo de provider;
- scan estático da fonte não encontrou subprocess, socket, requests, Popen,
  `shell=True`, `os.system`, eval ou exec no runtime.

O projeto não tem dependências runtime externas. Scanners opcionais como
`pip-audit`, Bandit e Semgrep não fazem parte do ambiente local desta rodada;
por isso não há alegação de cobertura deles. A sandbox hostil de código de
terceiros e locking multi-processo permanecem fora do escopo P2.
