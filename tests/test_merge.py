"""The non-destructive merge (#3), exercised against the real keepassxc-cli engine."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from conftest import (
    PASSWORD,
    add_entry,
    create_db,
    entry_password,
    list_entries,
    needs_keepassxc,
    set_entry_password,
)

from keepass_auto_merge import merge
from keepass_auto_merge.config import Config

pytestmark = needs_keepassxc


def config(watch: Path, **overrides: object) -> Config:
    return Config(watch_directory=watch, **overrides)


def diverged_copy(master: Path, dest: Path) -> Path:
    shutil.copy2(master, dest)
    return dest


def test_merges_every_conflict_file_into_the_master(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    first = diverged_copy(master, tmp_path / "keepass.sync-conflict-a.kdbx")
    add_entry(first, "one")
    second = diverged_copy(master, tmp_path / "keepass.sync-conflict-b.kdbx")
    add_entry(second, "two")

    report = merge.run(config(tmp_path), PASSWORD)

    assert report.failed == []
    assert "base" in list_entries(master)
    assert "one" in list_entries(master)
    assert "two" in list_entries(master)
    assert len(report.merged) == 2


def test_master_entries_absent_from_conflicts_are_preserved(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "only-in-master")
    conflict = diverged_copy(master, tmp_path / "keepass.sync-conflict-a.kdbx")
    add_entry(conflict, "from-conflict")

    merge.run(config(tmp_path), PASSWORD)

    assert "only-in-master" in list_entries(master)


def test_newer_conflict_entry_wins_and_history_is_kept(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "login")
    set_entry_password(master, "login", "master-old")
    conflict = diverged_copy(master, tmp_path / "keepass.sync-conflict-a.kdbx")
    # KeePass timestamps have one-second resolution: make the conflict genuinely newer.
    time.sleep(1.1)
    set_entry_password(conflict, "login", "conflict-new")

    merge.run(config(tmp_path), PASSWORD)

    assert entry_password(master, "login") == "conflict-new"


def test_master_is_backed_up_once_per_run(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    for name in ("a", "b"):
        add_entry(diverged_copy(master, tmp_path / f"keepass.sync-conflict-{name}.kdbx"), name)

    report = merge.run(config(tmp_path), PASSWORD)

    backups = sorted(tmp_path.glob(".keepass.kdbx.*.bak"))
    assert len(backups) == 1
    assert report.backup == backups[0]
    assert backups[0].name.startswith(".")


def test_backup_retention_prunes_old_backups(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    add_entry(diverged_copy(master, tmp_path / "keepass.sync-conflict-a.kdbx"), "a")
    for old in ("2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z"):
        shutil.copy2(master, tmp_path / f".keepass.kdbx.{old}.bak")

    merge.run(config(tmp_path, backup_keep=2), PASSWORD)

    assert len(list(tmp_path.glob(".keepass.kdbx.*.bak"))) == 2


def test_backup_can_be_disabled(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    add_entry(diverged_copy(master, tmp_path / "keepass.sync-conflict-a.kdbx"), "a")

    report = merge.run(config(tmp_path, backup_keep=0), PASSWORD)

    assert report.backup is None
    assert not list(tmp_path.glob("*.bak"))


def test_merged_conflict_files_are_archived(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    conflict = diverged_copy(master, tmp_path / "keepass.sync-conflict-a.kdbx")
    add_entry(conflict, "a")

    merge.run(config(tmp_path), PASSWORD)

    assert not conflict.exists()
    assert (tmp_path / ".merged" / conflict.name).is_file()


def test_merged_conflict_files_can_be_deleted(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    conflict = diverged_copy(master, tmp_path / "keepass.sync-conflict-a.kdbx")
    add_entry(conflict, "a")

    merge.run(config(tmp_path, on_merged="delete"), PASSWORD)

    assert not conflict.exists()
    assert not (tmp_path / ".merged").exists()


def test_failed_merge_leaves_the_master_exactly_as_it_was(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    before = master.read_bytes()
    broken = tmp_path / "keepass.sync-conflict-broken.kdbx"
    broken.write_bytes(b"this is not a kdbx file")

    report = merge.run(config(tmp_path), PASSWORD)

    assert master.read_bytes() == before
    assert broken.exists()
    assert len(report.failed) == 1
    assert report.failed[0][0] == broken


def test_a_failed_conflict_does_not_block_the_others(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    good = diverged_copy(master, tmp_path / "keepass.sync-conflict-good.kdbx")
    add_entry(good, "good-entry")
    broken = tmp_path / "keepass.sync-conflict-broken.kdbx"
    broken.write_bytes(b"garbage")

    report = merge.run(config(tmp_path), PASSWORD)

    assert "good-entry" in list_entries(master)
    assert len(report.merged) == 1
    assert len(report.failed) == 1


def test_master_is_replaced_by_rename_not_rewritten_in_place(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    add_entry(diverged_copy(master, tmp_path / "keepass.sync-conflict-a.kdbx"), "a")
    inode_before = os.stat(master).st_ino

    merge.run(config(tmp_path), PASSWORD)

    assert os.stat(master).st_ino != inode_before


def test_no_temporary_files_are_left_behind(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    add_entry(diverged_copy(master, tmp_path / "keepass.sync-conflict-a.kdbx"), "a")

    merge.run(config(tmp_path), PASSWORD)

    leftovers = [p.name for p in tmp_path.iterdir() if "tmp" in p.name or p.suffix == ".part"]
    assert leftovers == []


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    conflict = diverged_copy(master, tmp_path / "keepass.sync-conflict-a.kdbx")
    add_entry(conflict, "a")
    before = master.read_bytes()

    report = merge.run(config(tmp_path), PASSWORD, dry_run=True)

    assert master.read_bytes() == before
    assert conflict.exists()
    assert report.planned == [conflict]
    assert report.merged == []
    assert not list(tmp_path.glob(".keepass.kdbx.*.bak"))


def test_nothing_to_do_is_not_an_error(tmp_path: Path) -> None:
    create_db(tmp_path / "keepass.kdbx")

    report = merge.run(config(tmp_path), PASSWORD)

    assert report.merged == []
    assert report.failed == []


def test_two_stale_copies_that_only_add_entries_need_no_attention(tmp_path: Path) -> None:
    """Each conflict file is judged against the master as it was before the run began.

    Comparing later files against an already-merged master would make every multi-file run look
    like a deletion and turn the attention signal into noise.
    """
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "base")
    first = diverged_copy(master, tmp_path / "keepass.sync-conflict-a.kdbx")
    add_entry(first, "from-a")
    second = diverged_copy(master, tmp_path / "keepass.sync-conflict-b.kdbx")
    add_entry(second, "from-b")

    report = merge.run(config(tmp_path), PASSWORD)

    assert report.failed == []
    assert report.attention == []
    assert "from-a" in list_entries(master)
    assert "from-b" in list_entries(master)
