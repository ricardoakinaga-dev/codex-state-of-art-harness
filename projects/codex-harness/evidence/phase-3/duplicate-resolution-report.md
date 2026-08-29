# Duplicate resolution report

`duplicate-report.json` is the machine-readable result of the same bounded
scan. It reports same-byte copies, multiple versions, aliases/forks and
divergent bytes separately.

The real host has one blocking `DIVERGENT_BYTES` finding:
`engineering-framework`, version `0.1.0`, appears in two global roots with
different package hashes. Automatic resolution is blocked for that affected
version; a version pin cannot distinguish divergent bytes. This does not block
an unrelated clean version. Project/workspace precedence is applied only after
eligibility, compatibility, trust and divergence checks.
