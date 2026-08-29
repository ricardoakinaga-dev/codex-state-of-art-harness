# Duplicate and resolution report

The real host has one blocking duplicate finding:

| Capability | Version | Finding | Decision |
| --- | --- | --- | --- |
| `engineering-framework` | `0.1.0` | Same ID/version with divergent package bytes in `global.agents` and `global.codex` | Block until host cleanup or a verifier selects an exact content hash |

The resolver applies the documented precedence `explicit pin > project >
workspace > approved shared > global > system > external`. Identical bytes may
be deterministically resolved by precedence; a version pin alone cannot
distinguish divergent bytes with the same ID and version. Divergent bytes,
dependency cycles, version conflicts and unresolved required dependencies fail
closed. The CLI redacts both duplicate paths and never mutates either root.
