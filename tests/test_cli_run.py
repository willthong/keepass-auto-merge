"""`run` from the command line: reporting and exit codes."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import PASSWORD, add_entry, create_db, list_entries, needs_keepassxc

from keepass_auto_merge import cli

pytestmark = needs_keepassxc


@pytest.fixture
def watch(tmp_path: Path) -> Path:
    directory = tmp_path / "vaults"
    directory.mkdir()
    (tmp_path / "config.toml").write_text(f'watch_directory = "{directory}"\n', encoding="utf-8")
    return directory


@pytest.fixture
def credential(tmp_path: Path) -> Path:
    path = tmp_path / "cred"
    path.write_text(PASSWORD, encoding="utf-8")
    return path


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_run_merges_and_reports(watch: Path, credential: Path, capsys) -> None:
    master = create_db(watch / "keepass.kdbx")
    add_entry(master, "base")
    import shutil

    conflict = shutil.copy2(master, watch / "keepass.sync-conflict-a.kdbx")
    add_entry(Path(conflict), "a")

    code, out, _ = run(
        capsys,
        "run",
        "--config",
        str(watch.parent / "config.toml"),
        "--credential-file",
        str(credential),
    )

    assert code == 0
    assert "1" in out
    assert "a" in list_entries(master)


def test_run_exits_one_when_a_conflict_file_fails(watch: Path, credential: Path, capsys) -> None:
    create_db(watch / "keepass.kdbx")
    (watch / "keepass.sync-conflict-broken.kdbx").write_bytes(b"garbage")

    code, _, err = run(
        capsys,
        "run",
        "--config",
        str(watch.parent / "config.toml"),
        "--credential-file",
        str(credential),
    )

    assert code == 1
    assert "broken" in err


def test_run_dry_run_changes_nothing(watch: Path, credential: Path, capsys) -> None:
    master = create_db(watch / "keepass.kdbx")
    add_entry(master, "base")
    import shutil

    conflict = shutil.copy2(master, watch / "keepass.sync-conflict-a.kdbx")
    add_entry(Path(conflict), "a")
    before = master.read_bytes()

    code, out, _ = run(
        capsys,
        "run",
        "--dry-run",
        "--config",
        str(watch.parent / "config.toml"),
        "--credential-file",
        str(credential),
    )

    assert code == 0
    assert master.read_bytes() == before
    assert "dry run" in out.lower()


def test_run_without_credential_fails_clearly(watch: Path, tmp_path: Path, capsys) -> None:
    create_db(watch / "keepass.kdbx")

    code, _, err = run(
        capsys,
        "run",
        "--config",
        str(watch.parent / "config.toml"),
        "--credential-file",
        str(tmp_path / "missing-cred"),
    )

    assert code == 1
    assert "credential" in err.lower()


def test_deletion_in_conflict_file_is_logged_and_exits_two(
    watch: Path, credential: Path, capsys
) -> None:
    import subprocess

    master = create_db(watch / "keepass.kdbx")
    add_entry(master, "kept")
    add_entry(master, "removed")
    import shutil

    conflict = Path(shutil.copy2(master, watch / "keepass.sync-conflict-a.kdbx"))
    subprocess.run(
        ["keepassxc-cli", "rm", "-q", str(conflict), "removed"],
        input=f"{PASSWORD}\n",
        text=True,
        check=True,
        capture_output=True,
    )

    code, _, err = run(
        capsys,
        "run",
        "--config",
        str(watch.parent / "config.toml"),
        "--credential-file",
        str(credential),
    )

    assert code == 2
    assert "ERROR" in err
    assert "removed" in err
    assert "not a clean fast-forward" in err
    # non-destructive: the entry is still in the master
    assert "removed" in list_entries(master)


def test_clean_fast_forward_exits_zero(watch: Path, credential: Path, capsys) -> None:
    master = create_db(watch / "keepass.kdbx")
    add_entry(master, "base")
    import shutil

    conflict = Path(shutil.copy2(master, watch / "keepass.sync-conflict-a.kdbx"))
    add_entry(conflict, "added")

    code, _, err = run(
        capsys,
        "run",
        "--config",
        str(watch.parent / "config.toml"),
        "--credential-file",
        str(credential),
    )

    assert code == 0
    assert "ERROR" not in err
