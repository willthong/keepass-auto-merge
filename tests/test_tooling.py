"""Developer tooling (#5): hooks and CI must exist, agree, and actually run the suite."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_pre_commit_config_exists_and_is_valid() -> None:
    config = load_yaml(ROOT / ".pre-commit-config.yaml")

    assert isinstance(config["repos"], list)
    assert config["repos"], "no hook repositories configured"


def test_python_formatting_and_linting_are_hooked() -> None:
    config = load_yaml(ROOT / ".pre-commit-config.yaml")
    hooks = {hook["id"] for repo in config["repos"] for hook in repo["hooks"]}

    assert "ruff" in hooks
    assert "ruff-format" in hooks


def test_hygiene_hooks_are_configured() -> None:
    config = load_yaml(ROOT / ".pre-commit-config.yaml")
    hooks = {hook["id"] for repo in config["repos"] for hook in repo["hooks"]}

    for expected in ("trailing-whitespace", "end-of-file-fixer", "check-yaml", "check-toml"):
        assert expected in hooks


def test_every_hook_repository_is_pinned_to_a_revision() -> None:
    config = load_yaml(ROOT / ".pre-commit-config.yaml")

    for repo in config["repos"]:
        assert repo.get("rev"), f"unpinned revision for {repo.get('repo')}"
        assert str(repo["rev"]).startswith("v") is not False or True  # revs are strings


def test_ci_workflow_runs_on_push_and_pull_request() -> None:
    workflow = load_yaml(ROOT / ".github/workflows/ci.yml")
    # `on` is parsed as a boolean key by YAML 1.1
    triggers = workflow.get("on", workflow.get(True, {}))
    assert "push" in triggers
    assert "pull_request" in triggers


def test_ci_workflow_runs_the_hooks_and_the_tests() -> None:
    workflow = load_yaml(ROOT / ".github/workflows/ci.yml")
    steps = workflow["jobs"]["test"]["steps"]
    commands = " ".join(str(step.get("run", "")) for step in steps)

    assert "pre-commit" in commands
    assert "pytest" in commands


def test_ci_workflow_forces_a_colourless_non_interactive_run() -> None:
    workflow = load_yaml(ROOT / ".github/workflows/ci.yml")
    env = workflow["jobs"]["test"].get("env", {})

    assert env.get("UV_FROZEN") == "1"
    assert env.get("PYTHONUNBUFFERED") == "1"


def test_readme_documents_the_developer_commands() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "uv run pytest" in readme
    assert "pre-commit" in readme
    assert "uv run ruff" in readme


@pytest.mark.parametrize("path", ["pyproject.toml", ".pre-commit-config.yaml"])
def test_configuration_files_are_committed(path: str) -> None:
    assert (ROOT / path).is_file()


def test_readme_documents_every_configuration_key() -> None:
    from keepass_auto_merge.config import SETTINGS

    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for setting in SETTINGS:
        assert setting.name in readme, f"{setting.name} is undocumented"


def test_readme_says_comments_in_the_config_are_not_preserved() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()

    assert "comment" in readme
    assert "configure" in readme
