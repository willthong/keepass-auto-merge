"""Release (#8): a tag must produce installable artefacts with a matching version."""

from __future__ import annotations

import subprocess
import tomllib
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/release.yml"


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_release_workflow_exists() -> None:
    assert WORKFLOW.is_file()


def test_release_runs_on_version_tags() -> None:
    triggers = workflow().get("on", workflow().get(True, {}))
    tags = triggers["push"]["tags"]

    assert any(tag.startswith("v") for tag in tags)


def test_release_builds_a_wheel_and_a_deb() -> None:
    commands = " ".join(
        str(step.get("run", "")) for job in workflow()["jobs"].values() for step in job["steps"]
    )

    assert "uv build" in commands
    assert "packaging/build_deb.py" in commands


def test_release_attaches_the_artefacts() -> None:
    steps = [step for job in workflow()["jobs"].values() for step in job["steps"]]
    release_steps = [step for step in steps if "release" in str(step.get("uses", ""))]
    assert release_steps, "no release step"

    release = release_steps[0]["with"]
    files = str(release["files"])
    assert "*.whl" in files
    assert "*.deb" in files


def test_release_notes_are_generated_from_commits() -> None:
    steps = [step for job in workflow()["jobs"].values() for step in job["steps"]]
    release = next(step for step in steps if "release" in str(step.get("uses", "")))

    assert release["with"]["generate_release_notes"] is True


def test_the_wheel_builds_with_the_console_script(tmp_path: Path) -> None:
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    wheel = next(tmp_path.glob("keepass_auto_merge-*.whl"))
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    assert version in wheel.name

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "keepass_auto_merge/cli.py" in names
        entry_points = next(n for n in names if n.endswith("entry_points.txt"))
        assert "keepass-auto-merge" in archive.read(entry_points).decode()
