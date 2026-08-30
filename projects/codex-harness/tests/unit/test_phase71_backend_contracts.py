from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import harness_kernel.phase7_backend as backend
from harness_kernel.phase7_backend import (
    BACKEND_CAPABILITY_ID,
    BackendPackageContractError,
    validate_backend_benchmarks,
    validate_backend_evals,
    validate_backend_manifest,
    validate_backend_procedures,
)

PROJECT_ROOT = Path(__file__).parents[2]
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / BACKEND_CAPABILITY_ID


def _load(relative: str) -> dict[str, object]:
    return json.loads((PACKAGE_ROOT / relative).read_text(encoding="utf-8"))


def _has(errors: tuple[str, ...], expected: str) -> None:
    assert any(expected in error for error in errors), (expected, errors)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"{" + b'"a":' + b"[" * 65 + b"0" + b"]" * 65 + b"}", "nesting"),
        (b'{"a": 1, "a": 2}', "duplicate"),
        (b"not-json", "invalid JSON"),
        (b"[]", "must contain an object"),
        (b'{"number": NaN}', "invalid JSON"),
        (b"\xff", "invalid JSON"),
    ],
)
def test_strict_json_rejects_untrusted_metadata(payload: bytes, expected: str) -> None:
    with pytest.raises(BackendPackageContractError, match=expected):
        backend._strict_json(payload, label="fixture.json")


def test_strict_json_rejects_bounded_size_and_accepts_duplicate_free_objects() -> None:
    with pytest.raises(BackendPackageContractError, match="bounded size"):
        backend._strict_json(b"{" + b"x" * (backend._MAX_METADATA_BYTES + 1) + b"}", label="large")

    parsed = backend._strict_json(b'{"a": 1, "nested": {"b": true}}', label="small")
    assert parsed == {"a": 1, "nested": {"b": True}}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "must be a list"),
        ("not-a-list", "must be a list"),
        (["ok", "\x00bad"], "item is invalid"),
        (["ok", "x" * 5], "item is invalid"),
    ],
)
def test_bounded_strings_rejects_invalid_shape_and_items(value: object, expected: str) -> None:
    with pytest.raises(BackendPackageContractError, match=expected):
        backend._bounded_strings(value, "fields", maximum=4)


def test_bounded_strings_deduplicates_without_mutating_the_input() -> None:
    original = ["one", "one", "two"]
    assert backend._bounded_strings(original, "fields") == ("one", "two")
    assert original == ["one", "one", "two"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/absolute", "relative"),
        ("../escape", "traversal"),
        ("a/../b", "traversal"),
        ("", "invalid"),
    ],
)
def test_safe_path_parts_rejects_absolute_and_traversal_paths(value: str, expected: str) -> None:
    with pytest.raises(BackendPackageContractError, match=expected):
        backend._safe_path_parts(value, field="fixture path")


def test_safe_path_parts_normalizes_windows_separators_and_keeps_parts() -> None:
    assert backend._safe_path_parts("folder\\file.json", field="fixture path") == (
        "folder",
        "file.json",
    )


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda value: value.__setitem__("schema_version", "bad"), "schema_version is unsupported"),
        (lambda value: value.__setitem__("capability_id", "other"), "capability_id does not match"),
        (lambda value: value.__setitem__("version", "bad"), "version is invalid"),
        (lambda value: value.__setitem__("version", "0.2.0"), "version is not the bound"),
        (lambda value: value.__setitem__("type", "TOOL"), "manifest type is not"),
        (lambda value: value.__setitem__("role", "BUILDER"), "manifest role is not"),
        (lambda value: value.__setitem__("primary_type", "TOOL"), "manifest primary_type is not"),
        (lambda value: value.__setitem__("scope", []), "scope must be an object"),
        (
            lambda value: value["scope"].__setitem__("scope", "GLOBAL"),
            "scope is not project-local",
        ),
        (
            lambda value: value["scope"].__setitem__("activates_when", []),
            "activation contract is missing",
        ),
        (
            lambda value: value["scope"].__setitem__("do_not_activate_when", [""]),
            "do-not-activate contract is missing",
        ),
        (lambda value: value.__setitem__("contracts", []), "contracts must be an object"),
        (lambda value: value.__setitem__("composition", []), "composition must be an object"),
        (lambda value: value.__setitem__("dependencies", []), "dependencies must be an object"),
        (lambda value: value.__setitem__("compatibility", []), "compatibility must be an object"),
        (lambda value: value.__setitem__("provenance", []), "provenance must be an object"),
        (lambda value: value.__setitem__("security", []), "security must be an object"),
        (lambda value: value.__setitem__("status", "PROMOTED"), "status must remain CANDIDATE"),
        (lambda value: value.__setitem__("registry_bridge", True), "registry_bridge must be false"),
        (lambda value: value.__setitem__("metadata_only", False), "metadata_only must be true"),
        (lambda value: value.__setitem__("execution", "FULL"), "execution must be NONE"),
        (lambda value: value.__setitem__("read_only", False), "read_only must be true"),
        (
            lambda value: value.__setitem__("allowed_tools", ["shell"]),
            "allowed_tools must be empty",
        ),
    ],
)
def test_manifest_rejects_each_top_level_identity_and_boundary_violation(
    mutator, expected: str
) -> None:
    manifest = _load("manifest.json")
    mutator(manifest)
    _has(validate_backend_manifest(manifest), expected)


def test_manifest_reports_missing_required_fields_and_deduplicates_errors() -> None:
    errors = validate_backend_manifest({})
    assert "manifest missing schema_version" in errors
    assert "manifest missing execution_policy" in errors
    assert len(errors) == len(set(errors))


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (
            lambda value: value["scope"].__setitem__("installation_scope", "GLOBAL"),
            "scope is not project-local",
        ),
        (
            lambda value: value["scope"].__setitem__("activates_when", [1]),
            "activation contract is missing",
        ),
        (
            lambda value: value["scope"].__setitem__("do_not_activate_when", [" "]),
            "do-not-activate contract is missing",
        ),
        (
            lambda value: value["dependencies"].__setitem__("tools", ["tool"]),
            "dependencies.tools must be empty",
        ),
        (
            lambda value: value["dependencies"].__setitem__("providers", ["provider"]),
            "dependencies.providers must be empty",
        ),
    ],
)
def test_manifest_rejects_scope_and_dependency_boundary_variants(mutator, expected: str) -> None:
    manifest = _load("manifest.json")
    mutator(manifest)
    _has(validate_backend_manifest(manifest), expected)


@pytest.mark.parametrize("boundary", backend.BACKEND_FORBIDDEN_BOUNDARIES)
def test_manifest_rejects_security_boundary_mapping_and_scalar_variants(boundary: str) -> None:
    mapping_case = _load("manifest.json")
    mapping_case["security"][boundary] = {"allowed": True, "mode": "allow"}  # type: ignore[index]
    _has(validate_backend_manifest(mapping_case), f"security.{boundary} is not denied")

    scalar_case = _load("manifest.json")
    scalar_case["security"][boundary] = "ALLOW"  # type: ignore[index]
    _has(validate_backend_manifest(scalar_case), f"security.{boundary} is not denied")


def test_manifest_accepts_all_supported_security_denials() -> None:
    for denied in (False, "DENY", "deny", "DENIED", "denied", "NONE", "none"):
        manifest = _load("manifest.json")
        for boundary in backend.BACKEND_FORBIDDEN_BOUNDARIES:
            manifest["security"][boundary] = denied  # type: ignore[index]
        assert validate_backend_manifest(manifest) == ()


def test_manifest_reports_trust_provenance_contract_failures() -> None:
    manifest = _load("manifest.json")
    manifest["trust"] = None
    errors = validate_backend_manifest(manifest)
    _has(errors, "trust must be an object")

    manifest = _load("manifest.json")
    manifest["trust"]["level"] = "GLOBAL"  # type: ignore[index]
    manifest["trust"]["external_execution"] = "ALLOW"  # type: ignore[index]
    manifest["trust"]["promotion"] = ""  # type: ignore[index]
    manifest["provenance"] = {"source_type": "", "source_hashes": {"current": ""}}
    errors = validate_backend_manifest(manifest)
    _has(errors, "trust level")
    _has(errors, "external execution")
    _has(errors, "promotion rule")
    _has(errors, "provenance.source_type")
    _has(errors, "provenance.source_hashes")


@pytest.mark.parametrize(
    "field",
    (
        "source_type",
        "source_refs",
        "current_source_refs",
        "upstream_source_refs",
        "native_source_refs",
    ),
)
def test_manifest_provenance_accepts_scalar_source_refs_and_rejects_empty_values(
    field: str,
) -> None:
    manifest = _load("manifest.json")
    manifest["provenance"][field] = "source"  # type: ignore[index]
    assert f"provenance.{field} is incomplete" not in validate_backend_manifest(manifest)

    manifest["provenance"][field] = [""]  # type: ignore[index]
    _has(validate_backend_manifest(manifest), f"provenance.{field} is incomplete")


@pytest.mark.parametrize(
    "field",
    ("inputs", "outputs", "gates", "stop_conditions"),
)
def test_manifest_contract_lists_must_be_non_empty_string_lists(field: str) -> None:
    manifest = _load("manifest.json")
    manifest["contracts"][field] = [""]  # type: ignore[index]
    _has(validate_backend_manifest(manifest), f"contracts.{field} must be a non-empty string list")


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("same_invocation_role", "ANY", "same_invocation_role"),
        ("fresh_final_verification_required", False, "fresh final verification"),
        ("repair_limit", 2, "repair_limit"),
        ("can_call", "not-list", "composition.can_call must be a list"),
        ("can_be_called_by", "not-list", "composition.can_be_called_by must be a list"),
    ],
)
def test_manifest_composition_contract_is_bounded(field: str, value: object, expected: str) -> None:
    manifest = _load("manifest.json")
    manifest["composition"][field] = value  # type: ignore[index]
    _has(validate_backend_manifest(manifest), expected)


@pytest.mark.parametrize(
    "field",
    (
        "context_bytes",
        "selected_references_bytes",
        "procedures_per_run",
        "total_seconds",
        "attempts_per_procedure",
        "builder_invocations",
        "verifier_invocations",
        "composition_repairs",
        "evidence_records",
        "report_bytes",
        "max_no_progress_rounds",
        "unbounded_loops",
    ),
)
def test_manifest_budget_values_must_be_non_negative_integers(field: str) -> None:
    manifest = _load("manifest.json")
    manifest["budgets"][field] = True  # type: ignore[index]
    _has(validate_backend_manifest(manifest), f"budgets.{field} must be a non-negative integer")


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("attempts_per_procedure", 2, "attempts_per_procedure must be one"),
        ("unbounded_loops", 1, "unbounded_loops must be zero"),
        ("context_bytes", 0, "context_bytes is outside its bound"),
        ("total_seconds", 601, "total_seconds is outside its bound"),
        ("max_no_progress_rounds", 4, "max_no_progress_rounds is outside its bound"),
    ],
)
def test_manifest_budget_bounds_are_enforced(field: str, value: object, expected: str) -> None:
    manifest = _load("manifest.json")
    manifest["budgets"][field] = value  # type: ignore[index]
    _has(validate_backend_manifest(manifest), expected)


def test_manifest_quality_and_execution_policy_fail_closed() -> None:
    manifest = _load("manifest.json")
    manifest["quality"] = {"causal_claim": True}
    manifest["execution_policy"] = {"shell": "ALLOW", "allowed_tools": ["shell"]}
    errors = validate_backend_manifest(manifest)
    _has(errors, "quality.profile_refs is missing")
    _has(errors, "quality.causal_claim must be false")
    _has(errors, "execution_policy.network is missing")
    _has(errors, "execution_policy.shell is not denied")
    _has(errors, "execution policy has allowed tools")


@pytest.mark.parametrize("field", ("workspace_write", "arbitrary_interpolation", "subagents"))
def test_manifest_execution_policy_mutation_boundaries_are_denied(field: str) -> None:
    manifest = _load("manifest.json")
    manifest["execution_policy"][field] = "ALLOW"  # type: ignore[index]
    _has(validate_backend_manifest(manifest), f"execution_policy.{field} is not denied")


@pytest.mark.parametrize(
    ("catalog", "mutator", "expected"),
    [
        (
            "evals",
            lambda value: value.__setitem__("schema_version", "bad"),
            "schema_version is unsupported",
        ),
        (
            "evals",
            lambda value: value.__setitem__("package_id", "other"),
            "package_id does not match",
        ),
        ("evals", lambda value: value.__setitem__("scenarios", "bad"), "scenarios must be a list"),
        (
            "benchmarks",
            lambda value: value.__setitem__("schema_version", "bad"),
            "schema_version is unsupported",
        ),
        (
            "benchmarks",
            lambda value: value.__setitem__("package_id", "other"),
            "package_id does not match",
        ),
        ("benchmarks", lambda value: value.__setitem__("causal_claim", True), "causal claim"),
        ("benchmarks", lambda value: value.__setitem__("records", "bad"), "records must be a list"),
        (
            "procedures",
            lambda value: value.__setitem__("schema_version", "bad"),
            "schema is unsupported",
        ),
        (
            "procedures",
            lambda value: value.__setitem__("package_id", "other"),
            "package_id is not bound",
        ),
        ("procedures", lambda value: value.__setitem__("metadata_only", False), "metadata-only"),
        ("procedures", lambda value: value.__setitem__("execution", "run"), "cannot execute"),
        ("procedures", lambda value: value.__setitem__("read_only", False), "read-only"),
        (
            "procedures",
            lambda value: value.__setitem__("allowed_tools", ["tool"]),
            "no allowed tools",
        ),
    ],
)
def test_catalog_entry_points_accept_mappings_and_reject_top_level_contracts(
    catalog: str, mutator, expected: str
) -> None:
    value = _load(
        {
            "evals": "evals/scenarios.json",
            "benchmarks": "benchmarks/benchmark-fixtures.json",
            "procedures": "scripts/deterministic-procedures.json",
        }[catalog]
    )
    mutator(value)
    validator = {
        "evals": validate_backend_evals,
        "benchmarks": validate_backend_benchmarks,
        "procedures": validate_backend_procedures,
    }[catalog]
    _has(validator(value), expected)


def test_catalog_entry_points_support_directory_file_and_explicit_package_paths() -> None:
    assert validate_backend_evals(PACKAGE_ROOT) == ()
    assert validate_backend_evals(PACKAGE_ROOT / "evals" / "scenarios.json") == ()
    assert (
        validate_backend_evals(
            PACKAGE_ROOT / "evals" / "scenarios.json", package_path=PACKAGE_ROOT / "evals"
        )
        == ()
    )
    assert validate_backend_benchmarks(PACKAGE_ROOT) == ()
    assert (
        validate_backend_benchmarks(
            PACKAGE_ROOT / "benchmarks" / "benchmark-fixtures.json",
            package_path=PACKAGE_ROOT / "benchmarks",
        )
        == ()
    )
    assert validate_backend_procedures(PACKAGE_ROOT) == ()
    assert (
        validate_backend_procedures(
            PACKAGE_ROOT / "scripts" / "deterministic-procedures.json",
            package_path=PACKAGE_ROOT / "scripts",
        )
        == ()
    )


def test_catalog_entry_points_report_missing_files_and_invalid_json(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(BackendPackageContractError, match="unavailable"):
        validate_backend_evals(package)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    with pytest.raises(BackendPackageContractError, match="invalid JSON"):
        validate_backend_evals(invalid)


def test_eval_catalog_rejects_short_large_and_non_object_scenarios() -> None:
    catalog = _load("evals/scenarios.json")
    catalog["scenarios"] = []
    _has(validate_backend_evals(catalog), "at least 40")

    catalog = _load("evals/scenarios.json")
    catalog["scenarios"] = [copy.deepcopy(catalog["scenarios"][0])] * 129  # type: ignore[index]
    errors = validate_backend_evals(catalog)
    _has(errors, "exceeds its scenario bound")

    catalog = _load("evals/scenarios.json")
    catalog["scenarios"][0] = "not-object"  # type: ignore[index]
    _has(validate_backend_evals(catalog), "scenario 1 must be an object")


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("id", 1, "missing id"),
        ("category", "", "no category"),
        ("title", "", "invalid title"),
        ("input_identity", "", "invalid input_identity"),
        ("required_criterion_ids", [], "invalid required_criterion_ids"),
        ("evidence_refs", [""], "invalid evidence_refs"),
        ("input", {}, "incomplete input case"),
        ("preconditions", [], "invalid preconditions"),
        ("required_observations", [""], "invalid required_observations"),
        ("forbidden_observations", [], "invalid forbidden_observations"),
        ("expected_artifacts", [""], "invalid expected_artifacts"),
        ("known_bad", {}, "invalid known_bad case"),
        ("critical", "yes", "invalid critical flag"),
        ("expected_outcome", "UNKNOWN", "invalid expected outcome"),
    ],
)
def test_eval_catalog_rejects_each_scenario_field_variant(
    field: str, value: object, expected: str
) -> None:
    catalog = _load("evals/scenarios.json")
    scenario = copy.deepcopy(catalog["scenarios"][0])  # type: ignore[index]
    scenario[field] = value
    catalog["scenarios"] = [scenario]
    _has(validate_backend_evals(catalog), expected)


def test_eval_catalog_rejects_duplicate_ids_known_bad_outcome_and_non_contiguous_ids() -> None:
    catalog = _load("evals/scenarios.json")
    scenarios = copy.deepcopy(catalog["scenarios"])  # type: ignore[assignment]
    scenarios[1]["id"] = scenarios[0]["id"]
    _has(validate_backend_evals({**catalog, "scenarios": scenarios}), "not contiguous")

    catalog = _load("evals/scenarios.json")
    scenario = copy.deepcopy(catalog["scenarios"][0])  # type: ignore[index]
    scenario["known_bad"]["expected_outcome"] = scenario["expected_outcome"]  # type: ignore[index]
    _has(validate_backend_evals({**catalog, "scenarios": [scenario]}), "not distinct")


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("normalized_task", {}, "normalized_task.id is missing"),
        ("same_task", False, "same_task must be true"),
        ("records", [{"id": "x"}] * 5, "exactly four"),
        ("quality_invariants", {"false_critical_pass": 1}, "false_critical_pass"),
    ],
)
def test_benchmark_catalog_rejects_catalog_level_variants(
    field: str, value: object, expected: str
) -> None:
    catalog = _load("benchmarks/benchmark-fixtures.json")
    catalog[field] = value
    _has(validate_backend_benchmarks(catalog), expected)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("id", "", "missing id"),
        ("baseline", 1, "missing baseline"),
        ("task_id", "other", "does not match normalized task"),
        ("fixture_only", False, "fixture-only"),
        ("causal_claim", True, "causal claim"),
        ("expected_outcome", "UNKNOWN", "invalid expected outcome"),
        ("observation_status", "UNKNOWN", "invalid observation status"),
        ("observation", {}, "observation environment is missing"),
        ("observed", "yes", "observed flag is invalid"),
        ("context_bytes", True, "invalid context_bytes"),
        ("latency_ms", -1, "invalid latency_ms"),
    ],
)
def test_benchmark_catalog_rejects_record_variants(
    field: str, value: object, expected: str
) -> None:
    catalog = _load("benchmarks/benchmark-fixtures.json")
    record = copy.deepcopy(catalog["records"][0])  # type: ignore[index]
    record[field] = value
    catalog["records"] = [record]
    _has(validate_backend_benchmarks(catalog), expected)


def test_benchmark_catalog_rejects_record_duplicates_and_observation_invariants() -> None:
    catalog = _load("benchmarks/benchmark-fixtures.json")
    records = copy.deepcopy(catalog["records"])  # type: ignore[assignment]
    records[1]["id"] = records[0]["id"]
    _has(validate_backend_benchmarks({**catalog, "records": records}), "IDs must be unique")

    record = copy.deepcopy(catalog["records"][0])  # type: ignore[index]
    record["observation_status"] = "OBSERVED"
    record["observed"] = False
    record["observation"]["sample_count"] = 0  # type: ignore[index]
    record["observation"]["measurements"] = {}  # type: ignore[index]
    errors = validate_backend_benchmarks({**catalog, "records": [record]})
    _has(errors, "observed status has no samples")
    _has(errors, "observed measurements are missing")
    _has(errors, "observed flag disagrees")

    record = copy.deepcopy(catalog["records"][0])  # type: ignore[index]
    record["observation_status"] = "BLOCKED"
    record["observed"] = False
    record["observation"]["reason"] = ""  # type: ignore[index]
    _has(
        validate_backend_benchmarks({**catalog, "records": [record]}),
        "blocked status has no reason",
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("workspace_write", "allow", "workspace_write boundary"),
        ("arbitrary_interpolation", "allow", "arbitrary_interpolation boundary"),
        ("subagents", "allow", "subagents boundary"),
        ("procedures", None, "list is missing"),
        ("procedures", "bad", "must be a list"),
        ("procedures", [], "list is missing"),
    ],
)
def test_procedure_catalog_rejects_boundary_and_list_variants(
    field: str, value: object, expected: str
) -> None:
    catalog = _load("scripts/deterministic-procedures.json")
    catalog[field] = value
    _has(validate_backend_procedures(catalog), expected)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("id", "", "id is missing"),
        ("purpose", "", "purpose is empty"),
        ("inputs", [], "inputs is incomplete"),
        ("outputs", [""], "outputs is incomplete"),
        ("observation", 1, "observation is missing"),
        ("max_attempts", 2, "must have one attempt"),
        ("mutation", "write", "is mutating"),
    ],
)
def test_procedure_catalog_rejects_record_variants(
    field: str, value: object, expected: str
) -> None:
    catalog = _load("scripts/deterministic-procedures.json")
    procedure = copy.deepcopy(catalog["procedures"][0])  # type: ignore[index]
    procedure[field] = value
    catalog["procedures"] = [procedure]
    _has(validate_backend_procedures(catalog), expected)


def test_procedure_catalog_rejects_non_object_and_duplicate_records() -> None:
    catalog = _load("scripts/deterministic-procedures.json")
    _has(validate_backend_procedures({**catalog, "procedures": ["bad"]}), "must be an object")
    procedures = copy.deepcopy(catalog["procedures"])  # type: ignore[assignment]
    procedures[1]["id"] = procedures[0]["id"]
    _has(validate_backend_procedures({**catalog, "procedures": procedures}), "IDs must be unique")


def _metadata_inputs() -> tuple[dict[str, object], dict[str, dict[str, object]], tuple[str, ...]]:
    manifest = _load("manifest.json")
    documents = {
        relative: _load(relative)
        for relative in (
            "package-metadata.json",
            "composition-contract.json",
            "profiles.json",
            "eval-metadata.json",
            "benchmark-metadata.json",
        )
    }
    file_paths = tuple(
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in PACKAGE_ROOT.rglob("*")
        if path.is_file()
    )
    return manifest, documents, file_paths


def _metadata_errors(
    monkeypatch: pytest.MonkeyPatch,
    manifest: dict[str, object] | None = None,
    documents: dict[str, dict[str, object]] | None = None,
    file_paths: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    default_manifest, default_documents, default_file_paths = _metadata_inputs()
    selected_manifest = manifest if manifest is not None else default_manifest
    selected_documents = documents if documents is not None else default_documents
    selected_file_paths = file_paths if file_paths is not None else default_file_paths

    def read_document(_package: Path, relative: str, *, max_bytes: int) -> dict[str, object]:
        del max_bytes
        return copy.deepcopy(selected_documents[relative])

    monkeypatch.setattr(backend, "_read_package_json", read_document)
    return backend._validate_package_metadata(
        PACKAGE_ROOT,
        selected_manifest,
        selected_file_paths,
        scenario_count=48,
        benchmark_count=4,
    )


def test_package_metadata_declared_paths_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, documents, file_paths = _metadata_inputs()
    manifest["references"] = None
    manifest["profiles"] = ["missing.json"]
    manifest["dependencies"]["references"] = ["../unsafe.json"]  # type: ignore[index]
    errors = _metadata_errors(
        monkeypatch,
        manifest,
        documents,
        (*file_paths, "../unsafe.json"),
    )
    _has(errors, "manifest references must declare package paths")
    _has(errors, "manifest profiles references a missing package file")
    _has(errors, "manifest dependencies.references contains an unsafe path")


def test_package_metadata_missing_and_invalid_documents_are_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, documents, file_paths = _metadata_inputs()
    missing_paths = tuple(path for path in file_paths if path != "profiles.json")
    errors = _metadata_errors(monkeypatch, manifest, documents, missing_paths)
    _has(errors, "PACKAGE_METADATA_MISSING:profiles.json")

    def fail_document(_package: Path, relative: str, *, max_bytes: int):
        del max_bytes
        if relative == "package-metadata.json":
            raise BackendPackageContractError("malformed fixture")
        return copy.deepcopy(documents[relative])

    monkeypatch.setattr(backend, "_read_package_json", fail_document)
    errors = backend._validate_package_metadata(
        PACKAGE_ROOT,
        manifest,
        file_paths,
        scenario_count=48,
        benchmark_count=4,
    )
    _has(errors, "PACKAGE_METADATA_INVALID:package-metadata.json:malformed fixture")


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schema_version", "bad", "package-metadata.schema_version"),
        ("package_id", "other", "package-metadata.package_id"),
        ("native", False, "package-metadata.native"),
        ("scope", "GLOBAL", "package-metadata.scope"),
        ("version", "0.2.0", "package-metadata.version"),
        ("metadata_only", False, "package-metadata.metadata_only"),
        ("execution", "FULL", "package-metadata.execution"),
        ("host_load_claim", True, "package-metadata.host_load_claim"),
        ("global_state_mutation", True, "package-metadata.global_state_mutation"),
        ("installed_source_mutation", True, "package-metadata.installed_source_mutation"),
        ("external_state_mutation", True, "package-metadata.external_state_mutation"),
        ("package_write_allowed", True, "package-metadata.package_write_allowed"),
        ("no_false_causal_claim", False, "package-metadata.no_false_causal_claim"),
    ],
)
def test_package_metadata_identity_flags_are_bound(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object, expected: str
) -> None:
    manifest, documents, file_paths = _metadata_inputs()
    documents["package-metadata.json"][field] = value
    _has(_metadata_errors(monkeypatch, manifest, documents, file_paths), expected)


def test_package_metadata_requires_non_empty_claim_exclusions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, documents, file_paths = _metadata_inputs()
    documents["package-metadata.json"]["claims_excluded"] = []
    _has(
        _metadata_errors(monkeypatch, manifest, documents, file_paths),
        "claims_excluded must be non-empty",
    )


@pytest.mark.parametrize(
    "field",
    (
        "schema_version",
        "capability_id",
        "role",
        "authority",
        "pipeline",
        "can_call",
        "can_be_called_by",
        "must_run_after",
        "must_run_before",
        "conflicts",
        "do_not_combine",
        "optional",
        "handoff_edges",
        "fresh_final_verification",
        "repair_policy",
        "workspace_boundary",
        "support_levels",
        "causal_claim",
        "host_observability",
    ),
)
def test_composition_metadata_requires_every_contract_field(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    manifest, documents, file_paths = _metadata_inputs()
    documents["composition-contract.json"].pop(field)
    errors = _metadata_errors(monkeypatch, manifest, documents, file_paths)
    _has(errors, f"composition-contract missing {field}")


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schema_version", "bad", "schema is unsupported"),
        ("capability_id", "other", "capability_id is not bound"),
        ("role", "BUILDER", "role is not SPECIALIST"),
        ("causal_claim", True, "causal_claim must be false"),
        ("can_be_called_by", [], "can_be_called_by must be a non-empty list"),
        ("can_call", "bad", "can_call must be a list"),
        ("conflicts", ["X"], "conflicts disagrees with manifest"),
        ("do_not_combine", ["NOT_A_CONFLICT"], "do_not_combine must be conflicts subset"),
        ("fresh_final_verification", {}, "fresh verification is not required"),
        ("repair_policy", {}, "repair policy is not bounded to one"),
        ("workspace_boundary", {}, "package mutation is not denied"),
        ("support_levels", {}, "support levels are incomplete"),
    ],
)
def test_composition_metadata_rejects_bounded_contract_variants(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object, expected: str
) -> None:
    manifest, documents, file_paths = _metadata_inputs()
    documents["composition-contract.json"][field] = value
    _has(_metadata_errors(monkeypatch, manifest, documents, file_paths), expected)


@pytest.mark.parametrize("field", ("conflicts", "do_not_combine"))
def test_composition_metadata_must_agree_with_manifest(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    manifest, documents, file_paths = _metadata_inputs()
    manifest["composition"][field] = ["different"]  # type: ignore[index]
    _has(
        _metadata_errors(monkeypatch, manifest, documents, file_paths),
        f"{field} disagrees with manifest",
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schema_version", "bad", "profiles schema is unsupported"),
        ("capability_id", "other", "profiles capability_id is not bound"),
        ("profile_ids", [], "profile_ids must be non-empty"),
        ("default_profile", "MISSING", "default_profile is not declared"),
        ("profiles", "bad", "records do not match profile_ids"),
    ],
)
def test_profiles_metadata_rejects_identity_and_shape_variants(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object, expected: str
) -> None:
    manifest, documents, file_paths = _metadata_inputs()
    documents["profiles.json"][field] = value
    _has(_metadata_errors(monkeypatch, manifest, documents, file_paths), expected)


def test_profiles_metadata_rejects_duplicates_incomplete_and_unexpected_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, documents, file_paths = _metadata_inputs()
    profiles = documents["profiles.json"]
    profiles["profile_ids"] = ["DUP", "DUP"]
    _has(
        _metadata_errors(monkeypatch, manifest, documents, file_paths),
        "profile_ids must be non-empty",
    )

    manifest, documents, file_paths = _metadata_inputs()
    profiles = documents["profiles.json"]
    profiles["profiles"][0] = {}  # type: ignore[index]
    _has(
        _metadata_errors(monkeypatch, manifest, documents, file_paths),
        "incomplete profile contract",
    )

    manifest, documents, file_paths = _metadata_inputs()
    profiles = documents["profiles.json"]
    profiles["profiles"][0]["id"] = profiles["profiles"][1]["id"]  # type: ignore[index]
    _has(_metadata_errors(monkeypatch, manifest, documents, file_paths), "unexpected profile id")


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schema_version", "bad", "eval-metadata schema is unsupported"),
        ("package_id", "other", "eval-metadata package_id is not bound"),
        ("scenario_count", 47, "scenario_count does not match"),
        ("required_fields", [], "required_fields are incomplete"),
    ],
)
def test_eval_metadata_rejects_identity_and_shape_variants(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object, expected: str
) -> None:
    manifest, documents, file_paths = _metadata_inputs()
    documents["eval-metadata.json"][field] = value
    _has(_metadata_errors(monkeypatch, manifest, documents, file_paths), expected)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schema_version", "bad", "benchmark-metadata schema is unsupported"),
        ("package_id", "other", "benchmark-metadata package_id is not bound"),
        ("fixture_count", 3, "fixture_count does not match"),
        ("normalized_task", "other", "normalized task is not bound"),
    ],
)
def test_benchmark_metadata_rejects_identity_and_shape_variants(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object, expected: str
) -> None:
    manifest, documents, file_paths = _metadata_inputs()
    documents["benchmark-metadata.json"][field] = value
    _has(_metadata_errors(monkeypatch, manifest, documents, file_paths), expected)
