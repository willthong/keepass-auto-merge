"""The unconfigured state: what the tool cannot invent, and how it says so (#9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from keepass_auto_merge import cli
from keepass_auto_merge.config import Config, NotConfigured, load


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_missing_config_is_unconfigured(tmp_path: Path) -> None:
    with pytest.raises(NotConfigured) as raised:
        load(tmp_path / "gone.toml")

    assert "configure" in str(raised.value)


def test_config_without_watch_directory_is_unconfigured(tmp_path: Path) -> None:
    with pytest.raises(NotConfigured) as raised:
        load(write(tmp_path, 'master_filename = "x.kdbx"\n'))

    assert "watch_directory" in str(raised.value)


def test_watch_directory_that_is_not_a_directory_is_unconfigured(tmp_path: Path) -> None:
    missing = tmp_path / "gone"
    with pytest.raises(NotConfigured) as raised:
        load(write(tmp_path, f'watch_directory = "{missing}"\n'))

    assert "configure" in str(raised.value)


def test_unconfigured_message_tells_the_operator_what_to_run(tmp_path: Path) -> None:
    with pytest.raises(NotConfigured) as raised:
        load(tmp_path / "gone.toml")

    assert "keepass-auto-merge configure" in str(raised.value)


@pytest.mark.parametrize("verb", ["check", "run", "units"])
def test_every_verb_refuses_an_unconfigured_install(
    verb: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main([verb, "--config", str(tmp_path / "gone.toml")])
    err = capsys.readouterr().err

    assert code == 1
    assert "configure" in err


def test_a_config_with_no_watch_directory_does_not_crash_the_verb(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_file = write(tmp_path, 'conflict_glob = "*conflict*"\n')

    code = cli.main(["units", "--config", str(config_file)])

    assert code == 1
    assert "not configured" in capsys.readouterr().err


def test_every_setting_has_a_description_for_the_prompts() -> None:
    from keepass_auto_merge.config import SETTINGS

    assert SETTINGS
    for setting in SETTINGS:
        assert setting.description, f"{setting.name} has no description"
        assert setting.flag.startswith("--")


def test_documented_defaults_match_the_dataclass() -> None:
    from keepass_auto_merge.config import SETTINGS

    known = set(Config.__annotations__) - {"source"}
    assert {setting.name for setting in SETTINGS} == known
