# Capability discovery and inventory

The fresh real-host inventory contains 43 records:

| Root | Scope | Records |
| --- | --- | ---: |
| `project.harness` | PROJECT | 1 |
| `global.agents` | GLOBAL | 29 |
| `global.codex` | GLOBAL | 13 |

The unavailable project/system roots contribute no records. Thirty-seven
records are `SYNTHESIZED` from bounded `SKILL.md` metadata, five are `INVALID`
and one is `NATIVE` from the validated local `manifest.json`. Thirty-eight are
`INSPECTED`; five are `REJECTED` because they expose activation triggers
without a corresponding `do-not-activate` exclusion. Compatibility is `PARTIAL` for 42 and
`COMPATIBLE` for the project-local native record. Trust is
`THIRD_PARTY` for 37, `REJECTED` for five and `PROJECT_TRUSTED` for one. The
inventory records 102 references and 62 script entries as metadata only.

Each record carries a content hash, root scope, provenance, compatibility,
trust, lifecycle and load eligibility. The persisted JSON is sanitized and
does not expose raw host paths.
