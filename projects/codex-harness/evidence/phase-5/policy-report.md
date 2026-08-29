# Policy report

The policy is `P5-POLICY-1` and is parsed through the project-local allowlist.
The implementation now validates the configured fixed graph and every finite
budget field against the Phase 5 contract before accepting the policy.

The only graph is:

`DESIGN_BUILDER → STRUCTURAL_VERIFICATION → VISUAL_CRITIQUE → OPTIONAL_REPAIR → FINAL_VERIFICATION → ASSURANCE`

Budgets are two builder invocations, two structural verifications, two visual
critiques, one repair, two artifact versions, 131,072 artifact bytes, 32,768
context bytes and 64 evidence records. Any graph reorder, unknown budget,
budget drift or incomplete budget mapping is rejected.

The builder action policy is response-only and denies tools, executable
scripts, shell, network, MCP, providers, credentials and subagents. The
secondary capability is recorded as blocked, not as a permission-bearing
fallback.
