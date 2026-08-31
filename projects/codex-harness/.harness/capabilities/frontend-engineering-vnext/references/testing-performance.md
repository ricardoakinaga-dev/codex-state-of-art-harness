# Testing and performance contract

Test the changed risk, not a ritual. Pure state/validation rules get unit
tests; fixture/API boundaries get contract and integration tests; critical
flows get browser tests; negative paths cover empty, malformed, timeout,
error, retry, stale response, keyboard and double-submit behavior. The final
test command must run against the current artifact and report its exit code.

Build and type validation are stack-dependent. For TypeScript, run the
declared compiler and project build. For a no-dependency HTML/ES2022 surface,
run a deterministic build/packaging step, `node --check` for JavaScript
syntax, structural lint and the fixture/API tests; report that this is a
syntax/type analogue rather than pretending a TypeScript typecheck ran.

Performance evidence is observational and bounded: capture navigation and
resource timings, LCP when the browser exposes it, layout-shift observation,
font/media loading and oversized assets. Use declared budgets (default LCP
≤2500 ms and CLS ≤0.10) and record unavailable metrics honestly. Do not add
memoization, virtualization or code splitting without a measured problem.
