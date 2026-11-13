"""Discovery: which files in the watch directory take part in a run."""

from dataclasses import replace
from pathlib import Path

import pytest

from keepass_auto_merge.config import Config
from keepass_auto_merge.discovery import DiscoveryError, discover


def make_config(watch: Path, **overrides: object) -> Config:
    return replace(Config(watch_directory=watch), **overrides)


def touch(path: Path, mtime: int) -> Path:
    path.write_bytes(b"kdbx")
    import os

    os.utime(path, (mtime, mtime))
    return path


def test_finds_master_and_conflict_files(tmp_path: Path) -> None:
    master = touch(tmp_path / "keepass.kdbx", 100)
    conflict_a = touch(tmp_path / "keepass.sync-conflict-20240101.kdbx", 201)
    conflict_b = touch(tmp_path / "keepass.sync-conflict-20240102.kdbx", 202)

    found = discover(make_config(tmp_path))

    assert found.master == master
    assert set(found.conflicts) == {conflict_a, conflict_b}


def test_conflict_matching_is_case_insensitive(tmp_path: Path) -> None:
    touch(tmp_path / "keepass.kdbx", 100)
    upper = touch(tmp_path / "keepass.Sync-Conflict-1.kdbx", 201)

    found = discover(make_config(tmp_path))

    assert found.conflicts == [upper]


def test_custom_glob_is_honoured(tmp_path: Path) -> None:
    touch(tmp_path / "keepass.kdbx", 100)
    touch(tmp_path / "keepass.sync-conflict-1.kdbx", 200)
    dup = touch(tmp_path / "keepass (copy).kdbx", 201)

    found = discover(make_config(tmp_path, conflict_glob="*copy*"))

    assert found.conflicts == [dup]


def test_master_is_never_its_own_conflict_file(tmp_path: Path) -> None:
    touch(tmp_path / "keepass.kdbx", 100)

    found = discover(make_config(tmp_path, conflict_glob="*.kdbx"))

    assert found.conflicts == []


def test_archive_directory_is_excluded(tmp_path: Path) -> None:
    touch(tmp_path / "keepass.kdbx", 100)
    archive = tmp_path / ".merged"
    archive.mkdir()
    touch(archive / "keepass.sync-conflict-20230101.kdbx", 200)

    found = discover(make_config(tmp_path))

    assert found.conflicts == []


def test_conflicts_are_ordered_oldest_first(tmp_path: Path) -> None:
    touch(tmp_path / "keepass.kdbx", 100)
    newer = touch(tmp_path / "keepass.sync-conflict-newer.kdbx", 300)
    older = touch(tmp_path / "keepass.sync-conflict-older.kdbx", 200)

    found = discover(make_config(tmp_path))

    assert found.conflicts == [older, newer]


def test_missing_master_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="master database not found"):
        discover(make_config(tmp_path))


def test_nothing_to_do_when_no_conflict_files(tmp_path: Path) -> None:
    touch(tmp_path / "keepass.kdbx", 100)

    found = discover(make_config(tmp_path))

    assert found.conflicts == []
    assert found.master.is_file()
