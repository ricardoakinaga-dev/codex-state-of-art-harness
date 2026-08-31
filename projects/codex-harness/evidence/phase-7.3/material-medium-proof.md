# Phase 7.3 Material Medium Proof Matrix

This matrix is the separately reviewable proof required for every
`MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE` Medium residual.

- material Medium records: `64`
- proof records: `64`
- exact arcs claimed directly executed: `0`

The exact residual arc remains visible. This matrix does not turn a
neighboring test into branch coverage; it binds the source condition,
target, prior traceability and contract evidence for independent review.

## Records

| Branch ID | Source | Target | Category | Mapping | Proof status |
| --- | --- | --- | --- | --- | --- |
| `P7.2-BRANCH-037cdb723783aa3d` | `src/harness_kernel/phase4_execution.py:422` | `with suppress(OSError):` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-050c6379469b20e6` | `src/harness_kernel/phase7_host.py:1400` | `instruction = (` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-058da4b0fe41749c` | `src/harness_kernel/phase7_host.py:1653` | `return client` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-086761c2b5e2127e` | `src/harness_kernel/phase4_host.py:1131` | `if mcp_event_count:` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-0aad4a176d8bea4f` | `src/harness_kernel/phase4_execution.py:621` | `with suppress(OSError):` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-0b20e966b2308310` | `src/harness_kernel/phase4_execution.py:240` | `with suppress(OSError):` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-0d0b6bd817582a9b` | `src/harness_kernel/phase4_execution.py:400` | `raise ReplayLedgerError("replay ledger anchor temporary file could not be created")` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-1668a47ddcd9586e` | `src/harness_kernel/phase4_host.py:1139` | `error_code = "HOST_RESULT_UNAVAILABLE"` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-187dfa725fccfa19` | `src/harness_kernel/execution.py:863` | `raise ValueError("task id does not match the supplied profile")` | `FILESYSTEM` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-1ac98838024442ce` | `src/harness_kernel/phase7_host.py:845` | `raise ValueError("request workspace is outside the configured project")` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-21e0b28c17311b06` | `src/harness_kernel/phase4_execution.py:245` | `raise ReplayLedgerError("replay ledger parent cannot be opened safely") from exc` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-28166862d0d2919b` | `src/harness_kernel/phase4_execution.py:288` | `if not isinstance(value, Mapping) or value.get("schema_version") != _LEDGER_ANCHOR_SCHEMA:` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-29cb2d4e71a73fcb` | `src/harness_kernel/phase4_execution.py:240` | `raise` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-2a1474c5317a9c13` | `src/harness_kernel/execution.py:2295` | `selected_capability = (` | `FAILURE_ROUTING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-2e7e053d8c4ed8bc` | `src/harness_kernel/phase7_host.py:2081` | `try:` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-340fd64b3a7b1b84` | `src/harness_kernel/phase7_backend.py:1192` | `errors.append(f"procedure catalog {field} boundary is not denied")` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-34a6bd2f71ffb44e` | `src/harness_kernel/phase4_host.py:521` | `with suppress(subprocess.TimeoutExpired):` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-3aeeadcf83d8efe0` | `src/harness_kernel/execution.py:1993` | `for artifact in result.artifacts:` | `PERSISTENCE` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-41a65bb60a4ef9e4` | `src/harness_kernel/phase7_host.py:579` | `return _tool_ok({"path": relative, "bytes": len(encoded)})` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-4211a904b313161a` | `src/harness_kernel/phase4_execution.py:350` | `<exit>` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-4274bcaf91f5cd0c` | `src/harness_kernel/phase4_execution.py:194` | `raise ReplayLedgerError("workspace cannot be opened safely") from exc` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-434b8c0db1f0f435` | `src/harness_kernel/phase4_execution.py:425` | `with suppress(OSError):` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-45ccec59dacda321` | `src/harness_kernel/phase6_verifier.py:68` | `return Claim(` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-5286152c1a9011a4` | `src/harness_kernel/phase4_execution.py:245` | `with suppress(OSError):` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-531d3d1fd1656f5f` | `src/harness_kernel/phase4_host.py:377` | `raise HostProtocolError("app-server stdin is unavailable")` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-537d146f4d4006fc` | `src/harness_kernel/phase4_execution.py:194` | `with suppress(OSError):` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-68e57b8f3536fe17` | `src/harness_kernel/phase4_host.py:883` | `(` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-6f6ed3fa970af6d1` | `src/harness_kernel/phase5_execution.py:509` | `events.append("ASSURANCE")` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-72ea0c64819cfba4` | `src/harness_kernel/phase4_execution.py:189` | `raise` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-74670393ad21c560` | `src/harness_kernel/boundary.py:229` | `raise BoundaryError("JSONL append locking is unavailable")` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-784a54b8ec39095a` | `src/harness_kernel/phase7_host.py:1884` | `return False` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-85756ac0f904a37a` | `src/harness_kernel/phase7_host.py:1409` | `continue` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-869675de46e5aaec` | `src/harness_kernel/execution.py:203` | `raise ValueError(f"{label} is invalid")` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-89dc4d1ab77e904f` | `src/harness_kernel/execution.py:2482` | `outcome = self._execute_one(` | `NO_PROGRESS` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-8f445d6b7f619d3a` | `src/harness_kernel/phase7_host.py:516` | `return _tool_ok({"path": relative, "content": text, "bytes": len(content)})` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-9a6ef797c23f707d` | `src/harness_kernel/execution.py:2157` | `selected_capability = (` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-9a7b25c60ee25672` | `src/harness_kernel/phase4_execution.py:533` | `raise ReplayLedgerError("replay ledger token is invalid")` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-9abfc2537b5b7d32` | `src/harness_kernel/execution.py:2121` | `graph_deadline = graph_started + graph_duration_ms / 1000` | `NO_PROGRESS` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-a314146bb207e4a9` | `src/harness_kernel/phase4_host.py:521` | `try:` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-a59a45989beba51a` | `src/harness_kernel/phase4_execution.py:596` | `raise ReplayLedgerError("replay ledger temporary file could not be created")` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-a67a77f5c2fd8aed` | `src/harness_kernel/phase7_backend.py:209` | `return limits` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-a96e3638978ff832` | `src/harness_kernel/persistence.py:327` | `for parsed in existing:` | `PERSISTENCE` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-aed60be2d8987667` | `src/harness_kernel/phase4_execution.py:306` | `raise ReplayLedgerError("replay ledger anchor token is invalid")` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-b1d10822ff055338` | `src/harness_kernel/phase7_host.py:1595` | `write_error = "HOST_TOOL_CONTEXT_MISSING"` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-b5e302fe7b993885` | `src/harness_kernel/persistence.py:122` | `raise` | `PERSISTENCE` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-b81c8ca5a42904f4` | `src/harness_kernel/phase4_host.py:1067` | `with self._active_lock:` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-bbac59fa1005461a` | `src/harness_kernel/phase7_host.py:2081` | `return tuple(dict.fromkeys(errors))` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-be4c06295d107c5b` | `src/harness_kernel/persistence.py:155` | `try:` | `PERSISTENCE` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-c4fe94403d558ad7` | `src/harness_kernel/phase7_host.py:1882` | `package_value = policy.package_path` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-c69c6c5cf0a119f6` | `src/harness_kernel/phase4_execution.py:303` | `raise ReplayLedgerError("replay ledger anchor initialization state is invalid")` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-c6f47e9b16e68205` | `src/harness_kernel/phase7_host.py:1409` | `filtered.append(item)` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-c9999f77f2a92759` | `src/harness_kernel/execution.py:865` | `raise ValueError("run id does not match the supplied profile")` | `FILESYSTEM` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-cb35c195d7947478` | `src/harness_kernel/phase7_host.py:806` | `return False` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-ccb7ecf6b87c2c9e` | `src/harness_kernel/phase4_execution.py:618` | `with suppress(OSError):` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-dd2a25247bf92cb1` | `src/harness_kernel/boundary.py:256` | `raise BoundaryError("existing JSONL record is not an object")` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-e41b73baf50c28e0` | `src/harness_kernel/phase7_host.py:513` | `if parent_fd is not None:` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-e490a5fa17798622` | `src/harness_kernel/phase4_execution.py:189` | `with suppress(OSError):` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-e4b7bece9b93b8b4` | `src/harness_kernel/phase4_execution.py:527` | `if not isinstance(payload, Mapping) or payload.get("schema_version") != "P4-LEDGER-1":` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-e7db7fb71c6b8fd8` | `src/harness_kernel/phase4_execution.py:581` | `raise ReplayLedgerError("replay ledger is not a unique regular file")` | `LEDGER_LOCKING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-ed72f1fd56a3eb36` | `src/harness_kernel/phase6_checks.py:408` | `target, content = target_and_content` | `OTHER` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-f0517046b4c6e173` | `src/harness_kernel/routing.py:495` | `add(verifier, "provider output still needs independent contract verification")` | `FAILURE_ROUTING` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-f07295d8ac9ab7c5` | `src/harness_kernel/persistence.py:155` | `raise` | `PERSISTENCE` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-f63e9fdd57bbd76c` | `src/harness_kernel/phase4_host.py:745` | `(` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
| `P7.2-BRANCH-f7b719dacb595af6` | `src/harness_kernel/phase4_host.py:516` | `self._runtime_directory.cleanup()` | `HOST_AUTH` | `BEHAVIORAL_TARGETED_OR_REGRESSION` | `REVIEWABLE` |
