from __future__ import annotations

import json
import re
from pathlib import Path

from harness_kernel.phase3_discovery import CapabilityDiscovery
from harness_kernel.phase3_models import CapabilityKind, CapabilityRoot, RootScope
from harness_kernel.phase3_parser import ParseStatus, parse_skill_text

PROJECT_ROOT = Path(__file__).parents[2]
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "verification-loop-vnext"
MANIFEST_PATH = PACKAGE_ROOT / "manifest.json"
SKILL_PATH = PACKAGE_ROOT / "SKILL.md"

REQUIRED_PACKAGE_FILES = {
    "manifest.json",
    "SKILL.md",
    "profiles.json",
    "composition-contract.json",
    "package-metadata.json",
    "eval-metadata.json",
    "benchmark-metadata.json",
    "references/evidence-lineage.md",
    "references/role-boundaries.md",
    "references/deterministic-boundaries.md",
    "scripts/deterministic-procedures.json",
    "evals/scenarios.json",
    "benchmarks/benchmark-fixtures.json",
}
REQUIRED_COMPOSITION_FIELDS = {
    "can_call",
    "can_be_called_by",
    "must_run_before",
    "must_run_after",
    "conflicts_with",
    "conflicts",
    "optional",
    "do_not_combine",
}
REQUIRED_SECTIONS = {
    "identity",
    "purpose",
    "activate when",
    "do not activate when",
    "inputs",
    "outputs",
    "workflow",
    "deterministic checks",
    "roles/authority exclusions",
    "stop conditions",
    "evidence/freshness",
    "composition",
    "failure/degradation",
    "references",
}
REQUIRED_STOP_CONDITIONS = {
    "ALL_REQUIRED_CRITERIA_RESOLVED",
    "BLOCKING_FAILURE_FOUND",
    "MISSING_REQUIRED_TOOL",
    "MISSING_REQUIRED_ARTIFACT",
    "STALE_INPUT",
    "BUDGET_EXHAUSTED",
    "NO_PROGRESS",
    "REPEATED_PROCEDURE_FAILURE",
    "HUMAN_OVERRIDE",
}
DENIED_BOUNDARY_FIELDS = ("shell", "network", "mcp", "provider", "credential", "credentials")
UNSAFE_PACKAGE_FRAGMENTS = (
    "http://",
    "https://",
    "/home/",
    "/usr/",
    "/.agents/",
    "~/.",
    "subprocess",
    "os.system",
    "shell=true",
    "eval(",
    "exec(",
    "curl ",
    "wget ",
    "npm ",
    "pnpm ",
    "git ",
    "rm -rf",
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:api[_-]?key|password|secret|bearer|private[_-]?key)\s*[:=]\s*[\"'][^\"']+[\"']"
)


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_package_files() -> tuple[Path, ...]:
    return tuple(path for path in PACKAGE_ROOT.rglob("*") if path.is_file())


def _assert_denied(policy: dict[str, object], field: str) -> None:
    value = policy[field]
    if isinstance(value, dict):
        assert value.get("allowed") is False
        assert value.get("mode") == "deny"
    else:
        assert value in {False, "deny", "DENY"}


def test_phase6_package_shape_and_native_identity() -> None:
    assert PACKAGE_ROOT.is_dir()
    present = {path.relative_to(PACKAGE_ROOT).as_posix() for path in _all_package_files()}
    assert present >= REQUIRED_PACKAGE_FILES

    manifest = _load_json(MANIFEST_PATH)
    assert manifest["schema_version"] in {"CM-1", "P3-CM-1"}
    assert manifest["capability_id"] == "verification-loop-vnext"
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", str(manifest["version"]))
    assert manifest["primary_type"] == "VERIFIER"
    assert manifest["type"] == "VERIFIER"
    assert manifest["role"] == "VERIFIER"


def test_phase6_manifest_declares_project_verifier_contract() -> None:
    manifest = _load_json(MANIFEST_PATH)
    scope = manifest["scope"]
    assert isinstance(scope, dict)
    assert scope["scope"] == "PROJECT"
    assert scope["installation_scope"] == "PROJECT"
    assert scope["project_scope"] == "codex-state-of-art-harness"
    assert scope["activates_when"]
    assert scope["do_not_activate_when"]

    provenance = manifest["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["source_type"] == "PROJECT_LOCAL_NATIVE"
    assert provenance["source_refs"]
    assert provenance["current_source_refs"]
    assert provenance["project_scope"] == "codex-state-of-art-harness"
    assert provenance["source_repository"] == "local://codex-state-of-art-harness"

    composition = manifest["composition"]
    assert isinstance(composition, dict)
    assert composition.keys() >= REQUIRED_COMPOSITION_FIELDS
    assert composition["can_call"] == []
    assert composition["must_run_before"]
    assert composition["must_run_after"]

    dependencies = manifest["dependencies"]
    assert isinstance(dependencies, dict)
    assert dependencies["tools"] == []
    assert dependencies["providers"] == []
    assert manifest["allowed_tools"] == []

    contracts = manifest["contracts"]
    assert isinstance(contracts, dict)
    assert contracts["inputs"]
    assert contracts["outputs"]
    assert set(contracts["stop_conditions"]) >= REQUIRED_STOP_CONDITIONS

    for path_key in ("references", "scripts", "evals", "benchmarks"):
        entries = manifest[path_key]
        assert isinstance(entries, list) and entries
        assert all(isinstance(entry, str) for entry in entries)
        assert all((PACKAGE_ROOT / entry).is_file() for entry in entries)


def test_phase6_manifest_is_read_only_bounded_and_denies_external_boundaries() -> None:
    manifest = _load_json(MANIFEST_PATH)
    assert manifest["read_only"] is True
    assert manifest["security"]["read_only"] is True
    assert manifest["security"]["allowed_tools"] == []
    assert manifest["execution_policy"]["allowed_tools"] == []
    for policy in (manifest["security"], manifest["execution_policy"]):
        assert isinstance(policy, dict)
        for field in DENIED_BOUNDARY_FIELDS:
            _assert_denied(policy, field)

    budgets = manifest["budgets"]
    assert isinstance(budgets, dict)
    assert budgets["context_bytes"] <= 16 * 1024
    assert budgets["selected_references_bytes"] <= 64 * 1024
    assert budgets["procedures_per_run"] <= 32
    assert budgets["total_seconds"] <= 120
    assert budgets["attempts_per_procedure"] == 1
    assert budgets["verifier_invocations"] <= 2
    assert budgets["composition_repairs"] <= 1
    assert budgets["evidence_records"] <= 256
    assert budgets["report_bytes"] <= 128 * 1024
    assert budgets["unbounded_loops"] == 0


def test_phase6_package_is_discoverable_as_native_metadata_only_capability() -> None:
    root = CapabilityRoot(
        "phase6-project-capabilities",
        RootScope.PROJECT,
        str(PACKAGE_ROOT.parent),
        source="phase6-package-test",
    )
    inventory = CapabilityDiscovery().scan((root,))
    records = [
        item for item in inventory.capabilities if item.capability_id == "verification-loop-vnext"
    ]

    assert len(records) == 1
    record = records[0]
    assert record.kind is CapabilityKind.NATIVE
    assert record.manifest.capability_id == "verification-loop-vnext"
    assert record.manifest.primary_type == "VERIFIER"
    assert record.manifest.tools == ()
    assert record.manifest.providers == ()
    assert record.load_eligibility == "ELIGIBLE_DECLARATIVE_METADATA_ONLY"


def test_phase6_skill_has_valid_frontmatter_and_required_router_sections() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    document = parse_skill_text(skill, source="SKILL.md")

    assert document.status is ParseStatus.VALID
    assert document.capability_id == "verification-loop-vnext"
    assert document.primary_type == "VERIFIER"
    assert document.activates_when
    assert document.do_not_activate_when
    assert {section.title.casefold() for section in document.sections} >= REQUIRED_SECTIONS
    body = document.body.casefold()
    assert "not a builder" in body
    assert "not a director" in body
    assert "not a reviewer" in body
    assert "not an assurance" in body
    assert "not an orchestrator" in body
    assert "not a release authority" in body
    assert "does not judge visual quality" in body


def test_phase6_references_have_load_triggers_and_are_not_architecture_copies() -> None:
    manifest = _load_json(MANIFEST_PATH)
    references = manifest["references"]
    assert len(references) == len(set(references))
    for relative in references:
        path = PACKAGE_ROOT / relative
        assert relative.startswith("references/")
        content = path.read_text(encoding="utf-8")
        trigger_lines = [line for line in content.splitlines() if line.startswith("Load when:")]
        assert len(trigger_lines) == 1
        assert trigger_lines[0].removeprefix("Load when:").strip()
        assert "ADR-015" not in content
        assert "P6-QB-1" not in content


def test_phase6_script_entries_are_metadata_only() -> None:
    manifest = _load_json(MANIFEST_PATH)
    for relative in manifest["scripts"]:
        path = PACKAGE_ROOT / relative
        assert path.suffix == ".json"
        metadata = _load_json(path)
        assert metadata["metadata_only"] is True
        assert metadata["execution"] == "none"
        assert metadata["allowed_tools"] == []
        assert metadata["shell"] == "deny"
        assert metadata["network"] == "deny"
        assert metadata["credentials"] == "deny"


def test_phase6_package_contains_no_unsafe_tokens_urls_credentials_or_global_paths() -> None:
    files = _all_package_files()
    assert files
    for path in files:
        content = path.read_text(encoding="utf-8")
        folded = content.casefold()
        assert not any(fragment in folded for fragment in UNSAFE_PACKAGE_FRAGMENTS), path
        assert SECRET_ASSIGNMENT.search(content) is None, path
        assert "BEGIN PRIVATE KEY" not in content
        assert "sk-" not in folded
        assert "AKIA" not in content


def test_phase6_package_metadata_and_profiles_are_complete_without_host_load_claims() -> None:
    package_metadata = _load_json(PACKAGE_ROOT / "package-metadata.json")
    profiles = _load_json(PACKAGE_ROOT / "profiles.json")
    eval_metadata = _load_json(PACKAGE_ROOT / "eval-metadata.json")
    benchmark_metadata = _load_json(PACKAGE_ROOT / "benchmark-metadata.json")

    assert package_metadata["native"] is True
    assert package_metadata["scope"] == "PROJECT"
    assert package_metadata["host_load_claim"] is False
    assert package_metadata["package_id"] == "verification-loop-vnext"
    assert profiles["profile_ids"] == [
        "FOCUSED",
        "DOMAIN",
        "FULL",
        "VISUAL",
        "STRUCTURAL",
        "SECURITY_AWARE",
        "COMPOSITION",
    ]
    assert all(
        profile["visual_quality_authority"] == "EXCLUDED" for profile in profiles["profiles"]
    )
    assert eval_metadata["scenario_count"] >= 30
    assert benchmark_metadata["fixture_count"] == 4
