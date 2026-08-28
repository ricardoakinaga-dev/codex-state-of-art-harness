# Verification report

Provider execution não é evidence. O kernel cria `ArtifactRecord` com digest e
lineage, então `verify_provider_result` recalcula o digest do conteúdo e liga
claim, procedure e `EvidenceRecord` fresca. Output ausente, digest forjado,
artifact forjado, procedure não executada e evidence stale não podem virar
`PASS`.

`aggregate_verification` preserva claims `PASS`, `FAIL`, `NOT_RUN` e `UNKNOWN`;
assurance bloqueia ou falha quando há claim requerido não verificável. Critique
é `SEPARATED_SELF` no runtime local, com blind packet digest; uma revisão
independente de fase é necessária para o veredito final do pacote.

Os testes cobrem forged provider/artifact digest, procedure não executada,
stale propagation, assurance rejection, evidence limits, partial e not-run
summary states.
