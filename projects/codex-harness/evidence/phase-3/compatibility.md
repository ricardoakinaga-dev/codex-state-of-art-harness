# Compatibility report

`host compatibility --json` emits `P3-COMPATIBILITY-1` with status,
requirements, missing features, portability debt and confidence per record.
The real inventory reports 42 `PARTIAL` records with `INFERRED` confidence
because synthesized/legacy packages do not prove the native host contract;
five of those records are also rejected by the activation safety gate. The
project-local `harness-kernel` native manifest is `COMPATIBLE` with `OBSERVED`
confidence and its declared Python limit.

Incompatible records transition to `INCOMPATIBLE` and are not selectable. A
missing host signal remains `UNAVAILABLE` or `UNKNOWN`; it is never upgraded to
compatibility by directory presence alone. `capabilities compatibility` is an
alias for the same read-only report.
