# Error-path matrix

`TESTED` significa que a asserção verifica status, estado persistido, efeito,
telemetria ou evidência. `JUSTIFIABLY_NOT_APPLICABLE` só é usado quando a
operação não possui aquele tipo de caminho.

| Operação | Success | Validation | Auth | Not found | Conflict | Persistence | Dependency | Timeout | Cancel | Retry | Rollback | Partial | Unknown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| package/discovery | TESTED | TESTED | JNA | JNA | JNA | TESTED | TESTED | JNA | JNA | JNA | JNA | JNA | TESTED |
| builder/host | TESTED real | TESTED | TESTED | JNA | TESTED | TESTED | TESTED | TESTED | TESTED | TESTED | TESTED | TESTED | TESTED |
| appointment mutation | TESTED real | TESTED | TESTED | TESTED | TESTED | TESTED | TESTED | JNA | JNA | TESTED | TESTED | JNA | TESTED |
| migration | TESTED real | TESTED | JNA | JNA | TESTED | TESTED | JNA | JNA | JNA | TESTED | TESTED | JNA | TESTED |
| verifier/handoff | TESTED real | TESTED | TESTED | JNA | TESTED | TESTED | TESTED | TESTED | TESTED | TESTED | JNA | TESTED | TESTED |
| evidence/artifact | TESTED | TESTED | TESTED | TESTED | TESTED | TESTED | TESTED | TESTED | TESTED | JNA | TESTED | TESTED | TESTED |

Principais fontes: `tests/unit/test_phase71*.py`,
`pilots/backend-appointment-api/tests/test_pilot.py`,
`evidence/phase-7.1/catalog-evaluation.json` e os receipts em
`evidence/phase-7.1/real-rerun/`. A matriz não converte ausência de observação
do host em sucesso.
