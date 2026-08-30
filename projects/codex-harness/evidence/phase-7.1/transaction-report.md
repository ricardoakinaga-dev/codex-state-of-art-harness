# Transaction failure report

Resultado: `PASS_WITH_LIMITATIONS`.

- falha antes do primeiro write: paciente/cliente/provider inexistente retorna
  `NOT_FOUND` e não cria appointment nem chave de idempotência;
- falha durante migration: `test_injected_migration_failure_rolls_back_everything`
  observa banco sem tabelas após `MigrationError`;
- falha de persistência terminal: `test_terminal_ledger_write_failure_leaves_reservation_fail_closed`
  mantém a reserva `RESERVED_FOR_CONTROLLED_REAL`, sem reportar fechamento falso;
- commit/constraint: o piloto verifica `UNIQUE`, foreign keys, ownership
  triggers e rollback explícito após `IntegrityError`;
- duplicidade: replay persistente e concorrente não produz segunda mutação.

Asserções verificam contagem de linhas, chaves, registros relacionados,
checksum/estado de migration e artefatos, não apenas a exceção.
