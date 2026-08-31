# Phase 7.3 Coverage Delta Reconciliation

The authoritative Phase 7.2 branch set is compared with the final fresh
coverage-derived Phase 7.3 branch set by exact branch identity.

- removed from authoritative residual set: 77
- added to authoritative residual set: 0
- authoritative counts: {"high": 1, "low": 605, "medium": 186, "total": 792}
- current counts: {"high": 1, "low": 603, "medium": 111, "total": 715}

## Removed records

- P7.2-BRANCH-02937b0f68a2e439 — ['src/harness_kernel/validation.py', '_timestamp', 219, '_add('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-0b6dc054daacf524 — ['src/harness_kernel/phase3_host.py', 'CodexHostAdapter._existing_dir', 95, 'raise HostAdapterError(f"{label} is unavailable") from None'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-0e499287f043f791 — ['src/harness_kernel/phase6_models.py', 'VerificationOutput.__post_init__', 1213, 'object.__setattr__(self, "criterion_results", results)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-166fbddec5e6fa6b — ['src/harness_kernel/phase6_checks.py', 'run_deterministic_procedure', 470, 'return _result('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-16a66a02d81cd056 — ['src/harness_kernel/graph.py', 'validate_execution_graph', 149, 'findings.append('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-199541371d3533f8 — ['src/harness_kernel/phase4_host.py', 'CodexAppServerAdapter._event_from_message', 1323, 'load_values = tuple('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-1ac45c4927a73a23 — ['src/harness_kernel/classification.py', '_overall_confidence', 1246, 'return _enum(Confidence, explicit)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-1c74ce7f7a72bc75 — ['src/harness_kernel/phase6_models.py', '_output_status', 835, 'return VerificationStatus.NOT_RUN'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-1de738c1966d3628 — ['src/harness_kernel/phase6_models.py', '_optional_text', 114, 'return _text(value, name, maximum=maximum)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-20e51d428093ac96 — ['src/harness_kernel/classification.py', '_tuple_strings', 100, 'return ()'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-2273d37094632fed — ['src/harness_kernel/phase4_policy.py', 'PilotRule.__post_init__', 158, 'raise Phase4PolicyError("capability_id is invalid")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-242c4f38ac79356e — ['src/harness_kernel/classification.py', '_complexity_assessment', 526, 'value = _enum(Complexity, explicit)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-2ceff6432d136908 — ['src/harness_kernel/phase6_models.py', 'VerificationOutput.__post_init__', 1359, 'raise ValueError("PASS output requires a bound verification input")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-2dff379d249d734b — ['src/harness_kernel/phase6_checks.py', 'run_deterministic_procedure', 374, 'return _result('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-2e8bc22f6e32232f — ['src/harness_kernel/classification.py', '_data_assessment', 819, 'value = _enum(DataImpact, explicit)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-326f0b0383d54683 — ['src/harness_kernel/classification.py', '_enum', 115, 'raise TypeError(f"expected {enum_type.__name__} or string")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-34ee33bbc3057c36 — ['src/harness_kernel/phase3_resolution.py', 'ResolutionEngine.resolve', 273, 'raise ResolutionError("explicit version pin is invalid")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-366031303295ea96 — ['src/harness_kernel/phase6_models.py', 'VerificationOutput.__post_init__', 1368, 'claims = tuple(self.claims)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-40a15c05b84f3063 — ['src/harness_kernel/phase4_host.py', 'CodexAppServerAdapter._client', 745, 'raise HostProtocolError(self._host_binding_error or "HOST_EXECUTABLE_UNAVAILABLE")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-40d53fb73cbf4a2a — ['src/harness_kernel/phase4_host.py', 'CodexAppServerAdapter._client', 742, 'binding = self._resolved_host_binding()'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-423b8a346e5eeb1f — ['src/harness_kernel/phase3_resolution.py', 'ResolutionEngine._parse_request', 94, 'raise ResolutionError("capability request is invalid")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-45491e55c6a50b56 — ['src/harness_kernel/phase6_models.py', 'ProcedureResult.as_criterion_result', 713, 'raise ValueError("procedure result is missing its spec")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-454d5fca77d6a8ea — ['src/harness_kernel/registry.py', '_caret_bounds', 252, 'return lower, SemVer(1, 0, 0)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-48755d92f7883f60 — ['src/harness_kernel/phase5_verification.py', 'parse_blind_critique', 666, 'return VisualCritique('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-4c5e84528d093feb — ['src/harness_kernel/phase6_checks.py', 'run_deterministic_procedure', 443, 'return _result('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-51252b8f2124d3fc — ['src/harness_kernel/phase4_models.py', 'HostInvocationResult.__post_init__', 615, 'raise ValueError("completed_at cannot precede started_at")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-5146102e44e877ab — ['src/harness_kernel/phase3_resolution.py', 'ResolutionEngine._parse_request', 87, 'raise ResolutionError("capability request is invalid")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-516d01223ffaaeec — ['src/harness_kernel/phase3_discovery.py', 'CapabilityDiscovery._inspect_package', 529, 'kind = CapabilityKind.LEGACY'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-5898a76e63942c34 — ['src/harness_kernel/phase6_telemetry.py', 'Phase6TelemetryEvent.__post_init__', 61, 'raise Phase6TelemetryError("telemetry event_type is invalid")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-5b63a644f8442968 — ['src/harness_kernel/classification.py', '_reversibility_assessment', 1076, 'value = _enum(Reversibility, explicit)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-5c3b90331426310d — ['src/harness_kernel/classification.py', '_assessment_value', 130, 'raise TypeError('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-623a02afc20b5a8e — ['src/harness_kernel/phase6_models.py', '_output_freshness', 882, 'return FreshnessStatus.UNKNOWN'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-623e0a0f4b251294 — ['src/harness_kernel/phase7_host.py', 'VerificationLoopVNextAppServerAdapter._turn_params', 2050, 'return params'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-6412f54ed55c15a7 — ['src/harness_kernel/validation.py', '_nonnegative', 286, '_add('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-6bd1dd4cf1ce0a21 — ['src/harness_kernel/graph.py', 'execute_graph', 277, 'raise ValueError("max_invocations must be a non-negative integer or null")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-6c41bebcd73fec16 — ['src/harness_kernel/graph.py', 'execute_graph', 283, 'raise ValueError("max_duration_ms must be a non-negative integer or null")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-71c776e507350d4c — ['src/harness_kernel/phase6_checks.py', 'run_deterministic_procedure', 525, 'return _result('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-7429e3e4b068a7fd — ['src/harness_kernel/phase3_models.py', '_as_tuple', 142, 'return ()'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-77741988eb1af662 — ['src/harness_kernel/registry.py', 'parse_version_range', 306, 'raw = "*"'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-7ec6ee8f3c872b03 — ['src/harness_kernel/phase6_verifier.py', 'verify_input', 367, 'raise Phase6VerificationError("procedure result is missing its spec")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-88a71d1b17f4d34e — ['src/harness_kernel/phase4_models.py', '_as_tuple', 115, 'return ()'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-8c21492bcf878882 — ['src/harness_kernel/registry.py', '_next_bound', 245, 'return SemVer(major, minor, patch + 1)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-8c8615143cae2bb8 — ['src/harness_kernel/classification.py', '_parallel_assessment', 1026, 'value = _enum(ParallelismPotential, explicit)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-8fde3405f31a587c — ['src/harness_kernel/phase6_models.py', 'CriterionResult.__post_init__', 750, 'raise ValueError("criterion result procedure result is not bound")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-96c061644cdfe9f3 — ['src/harness_kernel/phase6_host.py', 'discover_vnext_package', 344, 'blockers.append("INSTRUCTION_KERNEL_UNAVAILABLE")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-97273df745cc88a4 — ['src/harness_kernel/phase6_models.py', 'CriterionResult.observed', 806, 'return "not observed"'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-995e56ddec8f6011 — ['src/harness_kernel/phase6_checks.py', 'run_deterministic_procedure', 506, 'return _result('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-9e5f883c0cb827d2 — ['src/harness_kernel/graph.py', 'validate_execution_graph', 110, 'findings.append('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-9e72ce149e2c1d68 — ['src/harness_kernel/phase3_telemetry.py', 'Phase3Telemetry.record_event', 156, 'raise TelemetryError("host stage event type is invalid")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-9f34eb8877e3e2a0 — ['src/harness_kernel/phase6_models.py', '_public', 254, 'return str(value)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-9fd0f959c4a05f5f — ['src/harness_kernel/phase6_models.py', 'VerificationOutput.__post_init__', 1257, 'expected_passed = tuple('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-b3a71b167d28a036 — ['src/harness_kernel/graph.py', 'execute_graph', 375, 'outcomes[node_id] = GraphNodeResult('] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-b6f7292bcfae4516 — ['src/harness_kernel/phase6_models.py', '_optional_text', 114, 'return None'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-b9aaee749c2236e8 — ['src/harness_kernel/classification.py', '_security_assessment', 741, 'value = _enum(SecurityImpact, explicit)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-bd0b31162c405c9d — ['src/harness_kernel/phase6_telemetry.py', 'Phase6Telemetry.record', 126, 'raise Phase6TelemetryError("telemetry event_type is invalid")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-bfc40aa9b2848178 — ['src/harness_kernel/phase4_models.py', '_freeze_mapping', 104, 'return MappingProxyType({})'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-bffa11c05d796883 — ['src/harness_kernel/graph.py', 'validate_execution_graph', 108, 'findings.append(_finding("$.nodes[].budget.tokens", "node tokens must be non-negative"))'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-c1ba27019ca199ed — ['src/harness_kernel/phase6_models.py', 'VerificationOutput.__post_init__', 1372, 'object.__setattr__(self, "claims", claims)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-c4ccb3d27094e956 — ['src/harness_kernel/graph.py', 'validate_execution_graph', 81, 'findings.append(_finding("$.nodes", "max_nodes must be a positive integer or null"))'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-c5ea8750d2a273dd — ['src/harness_kernel/phase6_checks.py', 'run_deterministic_procedure', 602, 'valid = False'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-c778bb0cdbd9827b — ['src/harness_kernel/classification.py', '_visual_assessment', 901, 'value = _enum(VisualImportance, explicit)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-c7cf8ded3d494863 — ['src/harness_kernel/classification.py', '_user_assessment', 1206, 'value = _enum(UserImpact, explicit)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-c8c37464f8a8c7a1 — ['src/harness_kernel/phase3_models.py', '_map_proxy', 154, 'return MappingProxyType({})'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-d0fab05b4fb45a96 — ['src/harness_kernel/classification.py', '_research_assessment', 983, 'value = _enum(ResearchNeed, explicit)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-d22fdc1a09d97905 — ['src/harness_kernel/registry.py', '_next_bound', 241, 'raise SemVerError("wildcard range has no upper bound")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-d462751dba2bd69d — ['src/harness_kernel/phase4_host.py', '_SubprocessClient._read', 389, 'raise HostProtocolError("app-server stdout is unavailable")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-d752e7c0f3e581e2 — ['src/harness_kernel/phase6_models.py', 'VerificationOutput.__post_init__', 1500, 'raise ValueError("verification output exceeds the report byte budget")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-d7673e58a980b2a1 — ['src/harness_kernel/graph.py', 'validate_execution_graph', 147, 'findings.append(_finding("$.graph_budget.tokens", "graph tokens must be non-negative"))'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-e2b340a93d498138 — ['src/harness_kernel/phase6_models.py', 'VerificationOutput.__post_init__', 1486, 'raise ValueError("reviewer cannot be the artifact producer")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-e3918221cd9d41d2 — ['src/harness_kernel/phase7_host.py', 'BackendVerifierAppServerAdapter._policy_for_request', 1860, 'raise ValueError("filesystem policy is not host-bound")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-e3a758b76baea6b6 — ['src/harness_kernel/phase6_models.py', 'VerificationOutput.__post_init__', 1482, 'raise ValueError("reviewer must be an identified REVIEWER")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-e705a93f93db0625 — ['src/harness_kernel/phase6_verifier.py', '_result_for', 228, 'raise Phase6VerificationError("procedure result is missing its spec")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-e81d8593e5b265d5 — ['src/harness_kernel/phase4_host.py', '_SubprocessClient._read', 397, 'raise HostProtocolError("app-server exited before returning a response")'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-ea37bf1b2683e20b — ['src/harness_kernel/phase3_discovery.py', '_load_json.pairs', 147, 'return None, "manifest JSON must be an object"'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-ec4cf6d5e65e3e19 — ['src/harness_kernel/registry.py', '_tilde_bounds', 263, 'return lower, SemVer(1, 0, 0)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-f802bcc4983d1240 — ['src/harness_kernel/phase7_host.py', 'run_fixed_pytest', 288, '_terminate_process(process)'] — COVERED_BY_FINAL_FRESH_COVERAGE
- P7.2-BRANCH-fd530224fec77343 — ['src/harness_kernel/registry.py', 'SemVer.parse', 100, 'raise SemVerError("version must be a string")'] — COVERED_BY_FINAL_FRESH_COVERAGE


## Added records

No records.


A removed record means the exact branch is covered by the final fresh
measurement; it does not erase its historical Phase 7.2 identity.
