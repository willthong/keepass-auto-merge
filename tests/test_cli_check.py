"""The CLI as a user drives it: `check` reports the plan without touching anything."""

from pathlib import Path

import pytest

from keepass_auto_merge import cli


@pytest.fixture
def watch(tmp_path: Path) -> Path:
    directory = tmp_path / "vaults"
    directory.mkdir()
    (directory / "keepass.kdbx").write_bytes(b"master")
    (directory / "keepass.sync-conflict-1.kdbx").write_bytes(b"one")
    (directory / "keepass.sync-conflict-2.kdbx").write_bytes(b"two")
    (tmp_path / "config.toml").write_text(f'watch_directory = "{directory}"\n', encoding="utf-8")
    return tmp_path


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_check_lists_master_and_conflict_files(watch: Path, capsys) -> None:
    code, out, _ = run(capsys, "check", "--config", str(watch / "config.toml"))

    assert code == 0
    assert "keepass.kdbx" in out
    assert "keepass.sync-conflict-1.kdbx" in out
    assert "keepass.sync-conflict-2.kdbx" in out
    assert "2 conflict file" in out


def test_check_writes_nothing(watch: Path, capsys) -> None:
    before = {p.name: p.read_bytes() for p in (watch / "vaults").iterdir()}
    run(capsys, "check", "--config", str(watch / "config.toml"))
    after = {p.name: p.read_bytes() for p in (watch / "vaults").iterdir()}

    assert before == after


def test_check_reports_nothing_to_do(watch: Path, capsys) -> None:
    (watch / "vaults" / "keepass.sync-conflict-1.kdbx").unlink()
    (watch / "vaults" / "keepass.sync-conflict-2.kdbx").unlink()

    code, out, _ = run(capsys, "check", "--config", str(watch / "config.toml"))

    assert code == 0
    assert "nothing to do" in out.lower()


def test_missing_config_fails_with_a_clear_message(watch: Path, capsys) -> None:
    code, _, err = run(capsys, "check", "--config", str(watch / "gone.toml"))

    assert code == 1
    assert "config file not found" in err


def test_missing_master_database_fails(watch: Path, capsys) -> None:
    (watch / "vaults" / "keepass.kdbx").unlink()

    code, _, err = run(capsys, "check", "--config", str(watch / "config.toml"))

    assert code == 1
    assert "master database not found" in err


def test_version_is_reported(capsys) -> None:
    code, out, _ = run(capsys, "--version")

    assert code == 0
    assert "keepass-auto-merge" in out


def test_unknown_command_is_usage_error(capsys) -> None:
    code, _, err = run(capsys, "frobnicate")

    assert code == 2
    assert "frobnicate" in err
