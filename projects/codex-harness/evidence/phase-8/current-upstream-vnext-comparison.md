# Current vs upstream vs Codex-native vNext

| Dimension | Installed current | Captured upstream | frontend-engineering-vNext |
| --- | --- | --- | --- |
| Package form | Legacy `SKILL.md` + agent metadata | Legacy `SKILL.md` with metadata | Native project-local manifest + router + typed declarative references |
| Identity | No version/fingerprint contract | No version/fingerprint contract | `frontend-engineering-vnext@0.1.0`, exact package fingerprint |
| Default stack | React/Next implied | React/Next more explicit | Existing-stack first; framework only when repository evidence supports it |
| State/interaction | Examples, no acceptance | Examples, no acceptance | State matrix, recovery, focus and double-submit contracts |
| Visual responsibility | Blended into frontend tips | Blended into frontend tips | Separate from `design-director`; render evidence required for visual claims |
| Verification | Not defined | Not defined | Fresh read-only `verification-loop-vnext` handoff |
| Security | Partial privacy guidance in fork | No native security route | Explicit handoff, no self-certification |
| Tool boundary | Unspecified | Unspecified | Bounded local tools; no package-owned shell/network/provider/credential authority |
| Eval/benchmark | None in package | None in package | 60 task-shaped evals and four viewport/state benchmark matrix |
| Portability debt | High | High | Reduced for existing web stack; React/SSR/native-mobile remain out of scope |

## Migration posture

This package is a bounded candidate and not a transparent drop-in replacement
for the installed skill. A future migration would need a compatibility matrix,
behavioral comparison, dependency decision, host-load observation and a new
review. The present phase proves only the observed pilot scope.
