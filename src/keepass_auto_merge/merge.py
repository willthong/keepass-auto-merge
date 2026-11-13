"""Non-destructive merge: every conflict file folded into the master, nothing lost.

The master is never written in place. It is copied to a temporary sibling, the merge runs against
that copy, and the copy is renamed over the master, so an interrupted run leaves the previous
master intact. Conflict files are opened read-only and only moved or deleted after a successful
merge.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .discovery import discover
from .engine import export_xml, merge_into
from .fastforward import classify, parse_export

BACKUP_SUFFIX = ".bak"


@dataclass(frozen=True)
class RunReport:
    planned: list[Path] = field(default_factory=list)
    merged: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    archived: list[Path] = field(default_factory=list)
    deleted: list[Path] = field(default_factory=list)
    backup: Path | None = None
    dry_run: bool = False
    attention: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed

    @property
    def needs_attention(self) -> bool:
        return bool(self.attention)


def run(config: Config, password: str, *, dry_run: bool = False) -> RunReport:
    found = discover(config)
    planned = found.conflicts
    if not planned:
        return RunReport(dry_run=dry_run)
    if dry_run:
        return RunReport(planned=list(planned), dry_run=True)

    backup = _backup_master(found.master, config) if config.backup_keep else None
    if config.on_merged == "archive":
        config.archive_path.mkdir(exist_ok=True)

    merged: list[Path] = []
    failed: list[tuple[Path, str]] = []
    archived: list[Path] = []
    deleted: list[Path] = []

    attention: list[str] = []
    for conflict in planned:
        try:
            attention.extend(_classify(found.master, conflict, password, cli=config.keepassxc_cli))
            _merge_one(found.master, conflict, password, cli=config.keepassxc_cli)
        except Exception as exc:
            failed.append((conflict, str(exc)))
            continue
        merged.append(conflict)
        if config.on_merged == "delete":
            conflict.unlink()
            deleted.append(conflict)
        else:
            destination = config.archive_path / conflict.name
            shutil.move(str(conflict), str(destination))
            archived.append(destination)

    if config.backup_keep:
        _prune_backups(found.master, config.backup_keep)

    return RunReport(
        planned=list(planned),
        merged=merged,
        failed=failed,
        archived=archived,
        deleted=deleted,
        backup=backup,
        attention=attention,
    )


def _classify(master: Path, conflict: Path, password: str, *, cli: str) -> list[str]:
    """Read-only: report anything about this merge that is not a clean fast-forward."""
    result = classify(
        parse_export(export_xml(master, password, cli=cli)),
        parse_export(export_xml(conflict, password, cli=cli)),
    )
    if result.clean:
        return []
    return result.report().splitlines()


def _merge_one(master: Path, conflict: Path, password: str, *, cli: str) -> None:
    handle, temp_name = tempfile.mkstemp(
        dir=master.parent, prefix=f".{master.name}.", suffix=".tmp"
    )
    os.close(handle)
    temp = Path(temp_name)
    try:
        shutil.copy2(master, temp)
        merge_into(temp, conflict, password, cli=cli)
        os.replace(temp, master)
    finally:
        temp.unlink(missing_ok=True)


def _backup_path(master: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return master.parent / f".{master.name}.{stamp}{BACKUP_SUFFIX}"


def _backup_master(master: Path, config: Config) -> Path:
    backup = _backup_path(master)
    shutil.copy2(master, backup)
    os.chmod(backup, 0o600)
    return backup


def _prune_backups(master: Path, keep: int) -> None:
    backups = sorted(master.parent.glob(f".{master.name}.*{BACKUP_SUFFIX}"))
    for stale in backups[:-keep] if keep else backups:
        stale.unlink(missing_ok=True)
