# Evidence staleness report

As suítes cobrem digest de package, artifact, criteria, migration, receipt,
builder handoff e verifier input. O catálogo Phase 7 observa `STALE_INPUT` ou
`MISSING_REQUIRED_CONTEXT` para artefato, receipt, package alias e contexto
substituídos. O verifier real recebeu um handoff ligado aos digests atuais e
observou o artefato sem alteração.

O pacote novo não reutiliza a revisão histórica como aprovação dos bytes
alterados: source/tests/config têm fingerprints atuais e o review final será
feito sobre este namespace `phase-7.1`.
