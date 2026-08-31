# Phase 7.3 Final Coverage Report

- initial test count: `1658`
- final test count: `1758`
- initial line coverage: `92.96055660715199%`
- final line coverage: `93.40563769376375%`
- initial branch coverage: `89.33674844971691%`
- final branch coverage: `90.36128336478835%`
- final statements: `19547`
- final covered lines: `18258`
- final missing lines: `1289`
- final total branches: `7418`
- final covered branches: `6703`
- final residual branches: `715`
- final high-risk residual branches: `1`
- final medium-risk residual branches: `111`
- final low-risk residual branches: `603`
- promotion-blocking high-risk branches: `0`

The line metric is coverage.py `percent_statements_covered`; the branch metric
is `percent_branches_covered`. The result is branch-aware and was generated
from the final source/test suite with no branch exclusions. The 77-ID delta
from the authoritative Phase 7.2 inventory is reconciled in
`coverage-delta-reconciliation.json`; missing arcs remain visible.

The one High record is separately closed as `UNREACHABLE_PROVEN` by the
Phase 7.2 CLI-loop proof. Current Medium materiality and closure are
authoritative in `medium-risk-inventory.json` and
`materiality-review.json`; 64 material Medium records additionally bind to
`material-medium-proof.json`. None of these artifacts claims direct execution
of a residual arc.
