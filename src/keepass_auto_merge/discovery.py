"""Discovery: find the master database and the conflict files waiting to be merged."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

from .config import Config


class DiscoveryError(Exception):
    """The watch directory does not hold what a run needs."""


@dataclass(frozen=True)
class Discovery:
    master: Path
    conflicts: list[Path]

    @property
    def has_work(self) -> bool:
        return bool(self.conflicts)


def discover(config: Config) -> Discovery:
    watch = config.watch_directory
    master = config.master_path
    if not master.is_file():
        raise DiscoveryError(f"master database not found: {master}")

    archive = config.archive_path.resolve()
    pattern = config.conflict_glob.lower()

    conflicts = [
        path
        for path in _kdbx_files(watch)
        if path != master
        and path.resolve().parent != archive
        and fnmatch.fnmatch(path.name.lower(), pattern)
    ]
    conflicts.sort(key=lambda path: (os.stat(path).st_mtime, path.name))
    return Discovery(master=master, conflicts=conflicts)


def _kdbx_files(watch: Path) -> list[Path]:
    return [entry for entry in watch.iterdir() if entry.is_file()]
