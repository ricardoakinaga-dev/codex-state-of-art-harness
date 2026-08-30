# Backend pilot and real composition regression

Piloto: `pilots/backend-appointment-api/`.

- pytest do piloto: `28 passed`;
- builder real isolado: `SUCCESS`, delta autorizado e paths limitados a
  `app/service.py` e `tests/test_pilot.py`;
- repair real bounded: `SUCCESS`, corrigindo apenas Ruff em
  `app/service.py` e `tests/test_pilot.py`;
- verifier real read-only em `real-rerun-final-2/`: `PASS_WITH_LIMITATIONS`,
  `local_checks.all_pass=true`, `host_report_valid=true`, workspace inalterado;
- catalog evaluation: 48/48, zero critical false pass e zero oracle mismatch.

Os receipts completos estão em `real-rerun-final-2/`. O host usa digests pinados do
Codex/Node local e mantém capability credentials negadas. Network/provider
absence é observação de protocolo bounded, não prova de isolamento por syscall.
