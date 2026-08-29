# Security and privacy checks

Passed checks:

- static Phase 3 runtime scan: no subprocess, shell, network, dynamic import,
  `eval`/`exec`, provider call or credential-read surface;
- evidence privacy scan: no raw Unix/Windows home-directory prefix or user name
  in the Phase 3 packet;
- `git diff --check`: pass;
- bounded parser/path/loader/eval tests: pass;
- all CLI refresh operations return `writes: []` and keep the host read-only.

`pip-audit` is **UNAVAILABLE** in the local environment (exit 127). This is
recorded as a limitation and is not represented as a passing dependency scan.
The adapter also cannot observe Codex runtime load causality, so it reports
`UNAVAILABLE`/`UNKNOWN` rather than inferring a successful load.
