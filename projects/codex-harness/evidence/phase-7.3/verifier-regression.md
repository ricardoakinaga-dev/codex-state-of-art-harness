# verification-loop-vNext Verifier Regression

- real cycle: `evidence/phase-7.3/real-cycle-report-005.json`
- builder: `PASS_WITH_LIMITATIONS`
- repair: `PASS_WITH_LIMITATIONS`
- verifier: `PASS_WITH_LIMITATIONS`
- fixed verifier tests: `29 passed`
- Ruff check: `PASS`
- Ruff format: `PASS`
- application mypy: `PASS`
- local verifier checks: `all_pass=true`
- verifier package fingerprint: `sha256:dc380396cdc489976b5d120a964321032907f0101431786cda060dae15c11a4b`
- status: `PASS_WITH_LIMITATIONS`

The host skill-load event is not observable from the local receipt; that is
retained as a limitation rather than inferred as a success.
