# Idempotency runtime

Status: `PASS_WITH_LIMITATIONS`

Concurrent submissions with one key produce one accepted and one duplicate response sharing the same intake id.

Primary packet references: `browser-evidence.json`, `runtime-eval-traceability.json`, `composition-proof.json`.
