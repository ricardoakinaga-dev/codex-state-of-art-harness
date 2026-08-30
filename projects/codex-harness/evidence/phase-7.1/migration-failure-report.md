# Migration failure report

O piloto real passou 28 testes, incluindo apply limpo, apply repetido,
inicialização concorrente, falha injetada com rollback completo, corrupção
detectada apesar do cache, trigger de ownership ineficaz, checksum drift,
duplicate migration, symlink e guards de entrada.

As migrations não contêm `DROP`/`TRUNCATE` destrutivo no fluxo aceito. Não há
uma matriz old-code/new-schema separada no fixture; isso é `JUSTIFIABLY_NOT_APPLICABLE`
para a API ficcional versionada apenas pelo checksum/ordem local, e permanece
uma limitação de escopo, não uma prova de compatibilidade universal.
