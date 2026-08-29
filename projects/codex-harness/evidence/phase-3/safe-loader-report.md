# Safe loader report

`safe-loader.json` records the five disclosure levels:

| Level | Behavior | Host load | Execution |
| --- | --- | --- | --- |
| L0 | identity only | unavailable | disabled |
| L1 | routing metadata/load plan | unavailable | disabled |
| L2 | bounded instruction kernel | unavailable | disabled |
| L3 | selected in-package references | unavailable | disabled |
| L4 | approved declarative package metadata | unavailable | `DISABLED_PHASE3` |

Reference paths are NUL-free, normalized, contained by the package and bounded
by file count, bytes and depth. Binary/sensitive/script/asset surfaces expose
metadata and hashes only; no script, provider, MCP, shell or network surface is
executed. `--explain` exposes the same eligibility, trust, compatibility,
precedence and execution boundary without exposing raw paths or content.
