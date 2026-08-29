# Phase 3 benchmark

`benchmark-summary.json` is a three-iteration local process baseline over the
real host. It covers root discovery, host snapshot, package discovery,
parsing/synthesis, duplicate analysis, compatibility, trust, registry bridge
and load-plan construction. The run observed five roots, 43 capability records
and six inventory errors.

Median wall-clock baselines were approximately 0.642 ms for root discovery,
300.961 ms for host snapshot, 307.922 ms for package discovery, 265.362 ms
for parse, 327.844 ms for manifest synthesis, 329.850 ms for duplicate
analysis, 259.582 ms for compatibility, 311.570 ms for trust, 0.293 ms for
the selected registry bridge and 0.120 ms for load-plan construction.

These figures are engineering diagnostics only. They do not measure production
latency, concurrency, provider/tool latency, host loading, quality, causal
impact or an SLO.
