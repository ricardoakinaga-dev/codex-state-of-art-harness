# Phase 7.3 Branch-Local Materiality Review

This artifact is authoritative for the High/Medium branch-local materiality assessment.
It preserves exact source context and separates non-material defensive acceptance from
promotion-relevant closure evidence.

- records: 112
- summary: {"accepted_nonmaterial": 44, "high": 1, "medium": 111, "promotion_relevant": 64, "records": 112}

| Branch ID | Risk | Source | Target | Materiality | Closure |
| --- | --- | --- | --- | --- | --- |
| P7.2-BRANCH-00fdf1c4330495a1 | medium | src/harness_kernel/phase3_parser.py:_scalar_metadata:107 | raise _MetadataStructureError("front matter metadata contains NUL") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-037cdb723783aa3d | medium | src/harness_kernel/phase4_execution.py:_set_ledger_anchor_state:422 | with suppress(OSError): | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-050c6379469b20e6 | medium | src/harness_kernel/phase7_host.py:BackendBuilderAppServerAdapter._with_instruction_kernel:1400 | instruction = ( | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-058da4b0fe41749c | medium | src/harness_kernel/phase7_host.py:BackendBuilderAppServerAdapter._client:1653 | return client | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-086761c2b5e2127e | medium | src/harness_kernel/phase4_host.py:CodexAppServerAdapter.request_invocation:1131 | if mcp_event_count: | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-0aad4a176d8bea4f | medium | src/harness_kernel/phase4_execution.py:_write_ledger:621 | with suppress(OSError): | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-0b20e966b2308310 | medium | src/harness_kernel/phase4_execution.py:_open_ledger_parent:240 | with suppress(OSError): | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-0d0b6bd817582a9b | medium | src/harness_kernel/phase4_execution.py:_set_ledger_anchor_state:400 | raise ReplayLedgerError("replay ledger anchor temporary file could not be created") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-0e6b0d8ab0c4fdfa | medium | src/harness_kernel/serialization.py:_convert:235 | return value | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-116fac858e80f593 | medium | src/harness_kernel/validation.py:_enum:192 | _add( | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-1469f5fdf2528f87 | medium | src/harness_kernel/phase3_parser.py:parse_skill_text:347 | errors.append("front matter name is missing or invalid") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-1668a47ddcd9586e | medium | src/harness_kernel/phase4_host.py:CodexAppServerAdapter.request_invocation:1139 | error_code = "HOST_RESULT_UNAVAILABLE" | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-187dfa725fccfa19 | medium | src/harness_kernel/execution.py:ExecutionKernel._profile:863 | raise ValueError("task id does not match the supplied profile") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-1ac98838024442ce | medium | src/harness_kernel/phase7_host.py:_bound_policy:845 | raise ValueError("request workspace is outside the configured project") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-1c294b042115cc67 | medium | src/harness_kernel/phase3_parser.py:_parse_front_matter:186 | if end is None: | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-1f3534c705ab446c | medium | src/harness_kernel/phase3_parser.py:_scalar_metadata:96 | return "" | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-21e0b28c17311b06 | medium | src/harness_kernel/phase4_execution.py:_open_ledger_parent:245 | raise ReplayLedgerError("replay ledger parent cannot be opened safely") from exc | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-2346e39eedb0ba49 | medium | src/harness_kernel/phase3_parser.py:_has_mapping_separator:89 | return True | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-27aaca73a85e9d12 | medium | src/harness_kernel/phase3_parser.py:_array_nesting_exceeds:53 | escaped = True | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-28166862d0d2919b | medium | src/harness_kernel/phase4_execution.py:_load_ledger_anchor:288 | if not isinstance(value, Mapping) or value.get("schema_version") != _LEDGER_ANCHOR_SCHEMA: | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-2974dea9bc7e64ef | medium | src/harness_kernel/cli.py:_config_result:421 | findings.append( | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-29cb2d4e71a73fcb | medium | src/harness_kernel/phase4_execution.py:_open_ledger_parent:240 | raise | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-2a1474c5317a9c13 | medium | src/harness_kernel/execution.py:ExecutionKernel._run_graph:2295 | selected_capability = ( | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-2e7e053d8c4ed8bc | medium | src/harness_kernel/phase7_host.py:VerificationLoopVNextAppServerAdapter.validate_invocation:2081 | try: | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-33582e85fea902c8 | medium | src/harness_kernel/phase3_parser.py:_parse_front_matter:195 | continue | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-340fd64b3a7b1b84 | medium | src/harness_kernel/phase7_backend.py:_validate_procedure_catalog:1192 | errors.append(f"procedure catalog {field} boundary is not denied") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-346f50743729f47a | medium | src/harness_kernel/phase3_parser.py:_has_mapping_separator:82 | escaped = True | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-34a6bd2f71ffb44e | medium | src/harness_kernel/phase4_host.py:_SubprocessClient.close:521 | with suppress(subprocess.TimeoutExpired): | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-3978024177b57dc2 | medium | src/harness_kernel/phase3_parser.py:_section_values:172 | for line in section.lines: | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-3a6d84625d69eeb6 | medium | src/harness_kernel/validation.py:_specific:503 | _nonempty(value.repair_of, "$.repair_of", findings, identifier=True) | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-3aeeadcf83d8efe0 | medium | src/harness_kernel/execution.py:ExecutionKernel._persist:1993 | for artifact in result.artifacts: | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-3f965afacb370036 | medium | src/harness_kernel/cli.py:main:1056 | raise CliError("INVALID_INPUT", "run id is invalid") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-40b01ca4858cba8b | medium | src/harness_kernel/phase3_models.py:public_data:751 | return str(value) | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-41a65bb60a4ef9e4 | medium | src/harness_kernel/phase7_host.py:BoundedBuilderHostTools._write:579 | return _tool_ok({"path": relative, "bytes": len(encoded)}) | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-4211a904b313161a | medium | src/harness_kernel/phase4_execution.py:_create_ledger_anchor:350 | <exit> | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-4274bcaf91f5cd0c | medium | src/harness_kernel/phase4_execution.py:_open_workspace_descriptor:194 | raise ReplayLedgerError("workspace cannot be opened safely") from exc | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-434b8c0db1f0f435 | medium | src/harness_kernel/phase4_execution.py:_set_ledger_anchor_state:425 | with suppress(OSError): | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-45ccec59dacda321 | medium | src/harness_kernel/phase6_verifier.py:_claim:68 | return Claim( | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-4996278505be6ce5 | medium | src/harness_kernel/phase5_models.py:_strings:86 | raise ValueError(f"{name} contains an invalid string") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-4b19ebeca10a65d7 | medium | src/harness_kernel/phase5_execution.py:CompositionRunner.run:497 | packet = make_blind_packet(task, artifact, tuple(renders)) | UNREACHABLE_BY_CONTRACT | UNREACHABLE_PROVEN |
| P7.2-BRANCH-4ca1fc62f69ab6df | medium | src/harness_kernel/cli.py:main:1054 | raise CliError("INVALID_INPUT", "task id is invalid") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-5020ce346518bbab | medium | src/harness_kernel/phase5_models.py:AssuranceReport.__post_init__:714 | raise ValueError("support level is invalid") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-5286152c1a9011a4 | medium | src/harness_kernel/phase4_execution.py:_open_ledger_parent:245 | with suppress(OSError): | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-531d3d1fd1656f5f | medium | src/harness_kernel/phase4_host.py:_SubprocessClient._send:377 | raise HostProtocolError("app-server stdin is unavailable") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-537d146f4d4006fc | medium | src/harness_kernel/phase4_execution.py:_open_workspace_descriptor:194 | with suppress(OSError): | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-55bc73ac0b4c6192 | medium | src/harness_kernel/cli.py:main:1199 | raise CliError("INVALID_INPUT", "run id is invalid") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-5a3323cf7498e4e0 | medium | src/harness_kernel/phase3_parser.py:_items:135 | raise _MetadataStructureError("front matter structured list is malformed") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-5c522f0ede03d764 | medium | src/harness_kernel/phase5_execution.py:CompositionRunner.run:442 | events.append("VISUAL_CRITIQUE") | UNREACHABLE_BY_CONTRACT | UNREACHABLE_PROVEN |
| P7.2-BRANCH-5f0aef35035696f1 | medium | src/harness_kernel/phase5_models.py:VisualCritique.__post_init__:644 | raise ValueError("overall_score is outside 0..100") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-668f987b12ea299c | medium | src/harness_kernel/phase3_parser.py:_unquote:70 | return value | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-68e57b8f3536fe17 | medium | src/harness_kernel/phase4_host.py:CodexAppServerAdapter.request_invocation:883 | ( | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-6ec232f013799d0a | medium | src/harness_kernel/validation.py:validate:701 | _add(findings, ValidationCode.INVALID_TYPE, "$", "value is not a supported contract record") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-6f6ed3fa970af6d1 | medium | src/harness_kernel/phase5_execution.py:CompositionRunner.run:509 | events.append("ASSURANCE") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-710e268a34ab07cc | medium | src/harness_kernel/phase3_parser.py:_array_nesting_exceeds:51 | escaped = False | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-72ea0c64819cfba4 | medium | src/harness_kernel/phase4_execution.py:_open_workspace_descriptor:189 | raise | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-7366be3caa7bb144 | medium | src/harness_kernel/phase3_parser.py:parse_skill_text:306 | return SkillDocument( | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-74670393ad21c560 | medium | src/harness_kernel/boundary.py:ProjectBoundary.append_jsonl:229 | raise BoundaryError("JSONL append locking is unavailable") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-780ac49024cb02f2 | medium | src/harness_kernel/validation.py:_specific:616 | for index, dimension in enumerate(value.dimensions): | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-784a54b8ec39095a | medium | src/harness_kernel/phase7_host.py:BackendVerifierAppServerAdapter._skill_is_discovered:1884 | return False | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-78c40bd9254dbf5c | medium | src/harness_kernel/cli.py:main:1197 | raise CliError("INVALID_INPUT", "task id is invalid") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-82e701e895cf98fe | medium | src/harness_kernel/validation.py:ValidationResult.raise_for_error:148 | <exit> | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-85756ac0f904a37a | medium | src/harness_kernel/phase7_host.py:BackendBuilderAppServerAdapter._with_instruction_kernel:1409 | continue | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-869675de46e5aaec | medium | src/harness_kernel/execution.py:_id:203 | raise ValueError(f"{label} is invalid") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-89dc4d1ab77e904f | medium | src/harness_kernel/execution.py:ExecutionKernel._run_graph.invoke:2482 | outcome = self._execute_one( | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-8d9de4d455a9f1c5 | medium | src/harness_kernel/phase3_parser.py:_parse_front_matter:208 | errors.append("front matter line has no key separator") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-8ed7f3e8bc5607a7 | medium | src/harness_kernel/phase3_parser.py:parse_skill_text:253 | raise SkillParseError("skill text must be a NUL-free string") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-8f445d6b7f619d3a | medium | src/harness_kernel/phase7_host.py:BoundedBuilderHostTools._read:516 | return _tool_ok({"path": relative, "content": text, "bytes": len(content)}) | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-9a6ef797c23f707d | medium | src/harness_kernel/execution.py:ExecutionKernel._run_graph:2157 | selected_capability = ( | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-9a7b25c60ee25672 | medium | src/harness_kernel/phase4_execution.py:_load_ledger:533 | raise ReplayLedgerError("replay ledger token is invalid") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-9abfc2537b5b7d32 | medium | src/harness_kernel/execution.py:ExecutionKernel._run_graph:2121 | graph_deadline = graph_started + graph_duration_ms / 1000 | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-a0b0a31a69ebaefe | medium | src/harness_kernel/phase3_parser.py:_parse_front_matter:213 | errors.append(f"invalid front matter key: {key[:80]}") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-a0fcdd0683508261 | medium | src/harness_kernel/phase3_parser.py:parse_skill_text:284 | return SkillDocument( | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-a314146bb207e4a9 | medium | src/harness_kernel/phase4_host.py:_SubprocessClient.close:521 | try: | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-a59a45989beba51a | medium | src/harness_kernel/phase4_execution.py:_write_ledger:596 | raise ReplayLedgerError("replay ledger temporary file could not be created") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-a67a77f5c2fd8aed | medium | src/harness_kernel/phase7_backend.py:_limits_for_package:209 | return limits | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-a96e3638978ff832 | medium | src/harness_kernel/persistence.py:RunStore.append_lifecycle.validate_append:327 | for parsed in existing: | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-aed60be2d8987667 | medium | src/harness_kernel/phase4_execution.py:_load_ledger_anchor:306 | raise ReplayLedgerError("replay ledger anchor token is invalid") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-b1d10822ff055338 | medium | src/harness_kernel/phase7_host.py:BackendBuilderAppServerAdapter._handle_host_request:1595 | write_error = "HOST_TOOL_CONTEXT_MISSING" | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-b5e302fe7b993885 | medium | src/harness_kernel/persistence.py:RunStore._write_once_json:122 | raise | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-b81c8ca5a42904f4 | medium | src/harness_kernel/phase4_host.py:CodexAppServerAdapter.request_invocation:1067 | with self._active_lock: | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-b87914f5fad02540 | medium | src/harness_kernel/serialization.py:from_json:307 | payload, model_type = model_type, payload | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-bba95d14a7c5043f | medium | src/harness_kernel/validation.py:_enum:192 | return | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-bbac59fa1005461a | medium | src/harness_kernel/phase7_host.py:VerificationLoopVNextAppServerAdapter.validate_invocation:2081 | return tuple(dict.fromkeys(errors)) | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-be4c06295d107c5b | medium | src/harness_kernel/persistence.py:RunStore._write_once_bytes:155 | try: | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-c1f5f138ec9e711e | medium | src/harness_kernel/validation.py:_enum:191 | if not isinstance(value, str) or not value.strip(): | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-c2babec4af622c84 | medium | src/harness_kernel/phase3_parser.py:_has_mapping_separator:80 | escaped = False | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-c35191bf82a949e3 | medium | src/harness_kernel/cli.py:main:1219 | raise CliError("SIZE_LIMIT_EXCEEDED", "objective exceeds the supported size limit") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-c4fe94403d558ad7 | medium | src/harness_kernel/phase7_host.py:BackendVerifierAppServerAdapter._skill_is_discovered:1882 | package_value = policy.package_path | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-c69c6c5cf0a119f6 | medium | src/harness_kernel/phase4_execution.py:_load_ledger_anchor:303 | raise ReplayLedgerError("replay ledger anchor initialization state is invalid") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-c6f47e9b16e68205 | medium | src/harness_kernel/phase7_host.py:BackendBuilderAppServerAdapter._with_instruction_kernel:1409 | filtered.append(item) | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-c9999f77f2a92759 | medium | src/harness_kernel/execution.py:ExecutionKernel._profile:865 | raise ValueError("run id does not match the supplied profile") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-cb35c195d7947478 | medium | src/harness_kernel/phase7_host.py:_filesystem_policy_matches:806 | return False | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-ccb7ecf6b87c2c9e | medium | src/harness_kernel/phase4_execution.py:_write_ledger:618 | with suppress(OSError): | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-d0f1c76495957750 | medium | src/harness_kernel/phase3_parser.py:_parse_front_matter:190 | return values, lists, 0, ["front matter closing delimiter is missing"] | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-d43743b01b8d2f5d | medium | src/harness_kernel/phase3_parser.py:parse_skill_bytes:437 | raise SkillParseError("skill payload must be bytes") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-dd2a25247bf92cb1 | medium | src/harness_kernel/boundary.py:ProjectBoundary.append_jsonl:256 | raise BoundaryError("existing JSONL record is not an object") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-e269fb74035996b4 | medium | src/harness_kernel/phase3_parser.py:parse_skill_text:255 | return SkillDocument( | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-e41b73baf50c28e0 | medium | src/harness_kernel/phase7_host.py:BoundedBuilderHostTools._read:513 | if parent_fd is not None: | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-e490a5fa17798622 | medium | src/harness_kernel/phase4_execution.py:_open_workspace_descriptor:189 | with suppress(OSError): | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-e4b7bece9b93b8b4 | medium | src/harness_kernel/phase4_execution.py:_load_ledger:527 | if not isinstance(payload, Mapping) or payload.get("schema_version") != "P4-LEDGER-1": | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-e7db7fb71c6b8fd8 | medium | src/harness_kernel/phase4_execution.py:_write_ledger:581 | raise ReplayLedgerError("replay ledger is not a unique regular file") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-e8831ddeb10329a1 | medium | src/harness_kernel/cli.py:_load_contract:567 | raise CliError("INVALID_VERSION", "unsupported contract schema") | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-ed72f1fd56a3eb36 | medium | src/harness_kernel/phase6_checks.py:run_deterministic_procedure:408 | target, content = target_and_content | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-f0517046b4c6e173 | medium | src/harness_kernel/routing.py:minimum_route.add:495 | add(verifier, "provider output still needs independent contract verification") | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-f07295d8ac9ab7c5 | medium | src/harness_kernel/persistence.py:RunStore._write_once_bytes:155 | raise | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-f11f4b263b32d81d | medium | src/harness_kernel/serialization.py:to_primitive:111 | return to_primitive(value.value, path=path) | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-f2e9d9298c4f3336 | high | src/harness_kernel/phase5_cli.py:_run_builder:400 | request_for_evidence = requests[-1] if requests else None | UNREACHABLE_BY_CONTRACT | UNREACHABLE_PROVEN |
| P7.2-BRANCH-f548dbed5622a8c7 | medium | src/harness_kernel/registry.py:SemVer.parse.identifiers:113 | raise SemVerError(f"invalid semver identifier: {item!r}") | UNREACHABLE_BY_CONTRACT | UNREACHABLE_PROVEN |
| P7.2-BRANCH-f63e9fdd57bbd76c | medium | src/harness_kernel/phase4_host.py:CodexAppServerAdapter._client:745 | ( | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-f7b719dacb595af6 | medium | src/harness_kernel/phase4_host.py:_SubprocessClient.close:516 | self._runtime_directory.cleanup() | MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | TESTED_PASS |
| P7.2-BRANCH-face3bde83100aa4 | medium | src/harness_kernel/phase3_parser.py:_unquote:70 | return value[1:-1] | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
| P7.2-BRANCH-fceff0970443383a | medium | src/harness_kernel/phase3_parser.py:parse_skill_bytes:439 | return SkillDocument( | NON_MATERIAL_DEFENSIVE | ACCEPTED_NON_MATERIAL |
