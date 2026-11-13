"""Fast-forward classification (#4).

`keepassxc-cli merge` is always keep-newer: it never applies deletions. That is safe, but it hides
intent. Before merging we compare the two databases and say loudly whenever the merge is not a
clean fast-forward.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from conftest import (
    PASSWORD,
    add_entry,
    create_db,
    needs_keepassxc,
    set_entry_password,
)

from keepass_auto_merge.fastforward import classify, parse_export

pytestmark = needs_keepassxc


def export(path: Path, password: str = PASSWORD) -> str:
    result = subprocess.run(
        ["keepassxc-cli", "export", "-q", "-f", "xml", str(path)],
        input=f"{password}\n",
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def divergent_pair(tmp_path: Path) -> tuple[Path, Path]:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "shared")
    import shutil

    conflict = Path(shutil.copy2(master, tmp_path / "keepass.sync-conflict-a.kdbx"))
    return master, conflict


def test_conflict_that_only_adds_entries_is_a_clean_fast_forward(tmp_path: Path) -> None:
    master, conflict = divergent_pair(tmp_path)
    add_entry(conflict, "brand-new")

    result = classify(parse_export(export(master)), parse_export(export(conflict)))

    assert result.clean
    assert result.deletions == []
    assert result.master_newer == []


def test_identical_databases_are_a_clean_fast_forward(tmp_path: Path) -> None:
    master, conflict = divergent_pair(tmp_path)

    result = classify(parse_export(export(master)), parse_export(export(conflict)))

    assert result.clean


def test_entry_deleted_from_the_conflict_file_is_reported(tmp_path: Path) -> None:
    master, conflict = divergent_pair(tmp_path)
    add_entry(conflict, "stays")
    subprocess.run(
        ["keepassxc-cli", "rm", "-q", str(conflict), "shared"],
        input=f"{PASSWORD}\n",
        text=True,
        check=True,
        capture_output=True,
    )

    result = classify(parse_export(export(master)), parse_export(export(conflict)))

    assert not result.clean
    assert [entry.title for entry in result.deletions] == ["shared"]
    assert "shared" in result.report()


def test_entry_edited_only_in_the_conflict_file_is_clean(tmp_path: Path) -> None:
    master, conflict = divergent_pair(tmp_path)
    time.sleep(1.1)
    set_entry_password(conflict, "shared", "conflict-side")

    result = classify(parse_export(export(master)), parse_export(export(conflict)))

    assert result.clean


def test_entry_newer_in_the_master_is_reported(tmp_path: Path) -> None:
    master, conflict = divergent_pair(tmp_path)
    time.sleep(1.1)
    set_entry_password(master, "shared", "master-side")

    result = classify(parse_export(export(master)), parse_export(export(conflict)))

    assert not result.clean
    assert [entry.title for entry in result.master_newer] == ["shared"]


def test_entry_changed_on_both_sides_is_reported_as_such(tmp_path: Path) -> None:
    master, conflict = divergent_pair(tmp_path)
    time.sleep(1.1)
    set_entry_password(conflict, "shared", "conflict-side")
    time.sleep(1.1)
    set_entry_password(master, "shared", "master-side")

    result = classify(parse_export(export(master)), parse_export(export(conflict)))

    assert not result.clean
    assert [entry.title for entry in result.both_changed] == ["shared"]
    assert "changed on both sides" in result.report()


def test_classification_is_read_only(tmp_path: Path) -> None:
    master, conflict = divergent_pair(tmp_path)
    before = master.read_bytes()

    classify(parse_export(export(master)), parse_export(export(conflict)))

    assert master.read_bytes() == before


def test_unrelated_database_is_not_a_clean_fast_forward(tmp_path: Path) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    add_entry(master, "mine")
    other = create_db(tmp_path / "other.kdbx")
    add_entry(other, "theirs")

    result = classify(parse_export(export(master)), parse_export(export(other)))

    assert [entry.title for entry in result.added] == ["theirs"]
    assert [entry.title for entry in result.deletions] == ["mine"]
    assert not result.clean
