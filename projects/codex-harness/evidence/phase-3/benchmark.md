# Phase 3 benchmark

`benchmark-summary.json` is a three-iteration local process baseline from
`harness_kernel.phase3_benchmarks.run_phase3_benchmarks`. It uses a temporary
project-local synthetic scenario with 100 bounded declarative capability
packages and measures host snapshot, root discovery, package discovery,
parsing, manifest synthesis, duplicate analysis, compatibility, trust, registry
bridging and load-plan preparation.

These figures are engineering diagnostics only. They do not measure production
latency, concurrency, provider/tool latency, host loading, quality, causal
impact or an SLO.
