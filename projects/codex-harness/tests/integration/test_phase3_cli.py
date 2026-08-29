from __future__ import annotations

import json
from pathlib import Path

from harness_kernel.phase3_cli import main


def test_phase3_cli_host_inspect_is_json_and_read_only(tmp_path: Path, capsys: object) -> None:
    project = tmp_path / "project"
    project.mkdir()

    assert main(["--project-root", str(project), "host", "inspect", "--json"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    value = json.loads(output)

    assert value["host_id"] == "codex-host-local"
    assert value["observation_status"] == "OBSERVED"
    assert value["roots"]
    assert str(tmp_path) not in output

    assert main(["--json", "host", "roots"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == "P3-ROOTS-1"


def test_phase3_cli_resolve_and_load_plan_do_not_execute(tmp_path: Path, capsys: object) -> None:
    project = tmp_path / "project"
    package = project / ".agents" / "skills" / "demo"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\nactivates_when: demo\n"
        "do_not_activate_when: never demo\n---\nbody\n",
        encoding="utf-8",
    )

    assert main(["--project-root", str(project), "resolve", "demo", "--json"]) == 0
    resolved = json.loads(capsys.readouterr().out)
    assert resolved["status"] == "RESOLVED"
    assert resolved["selected"]

    assert (
        main(
            [
                "--project-root",
                str(project),
                "load-plan",
                "demo",
                "--level",
                "L2_INSTRUCTION_KERNEL",
                "--json",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["load_plan"]["actual_host_loaded"] is False
    assert str(project) not in json.dumps(plan)


def test_phase3_cli_duplicate_paths_are_redacted(tmp_path: Path, capsys: object) -> None:
    project = tmp_path / "project"
    for package_name, description in (("same-a", "first"), ("same-b", "second")):
        package = project / ".agents" / "skills" / package_name
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            f"---\nname: same\ndescription: {description}\n---\nbody\n",
            encoding="utf-8",
        )

    assert main(["--project-root", str(project), "host", "duplicates", "--json"]) == 0
    output = capsys.readouterr().out
    assert str(project) not in output
    assert "DIVERGENT_BYTES" in output
