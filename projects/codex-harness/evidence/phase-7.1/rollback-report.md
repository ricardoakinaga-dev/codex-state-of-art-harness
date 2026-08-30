# Rollback report

O piloto real passou os cenários de rollback de migration e de conflito de
slot. A suíte Phase 7.1 adiciona fault injection para escrita atômica, falha de
`fsync`, colisão de nome temporário, falha de commit/ledger e rollback do
descritor.

Evidência observada: migration com falha não deixa tabelas; conflito de slot
deixa exatamente um appointment; falha terminal de ledger mantém a reserva e
bloqueia replay; writers concorrentes preservam o snapshot existente. Falha do
próprio rollback é transformada em estado fail-closed ou erro tipado, nunca em
`PASS` implícito.
