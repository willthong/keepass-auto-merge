"""Configuration: a single TOML file describing the watch directory and merge behaviour.

The master password is deliberately absent: it lives in the system credential store (ADR-0002).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "watch_directory": None,
    "master_filename": "keepass.kdbx",
    "conflict_glob": "*sync-conflict*",
    "merge_mode": "keep-newer",
    "on_merged": "archive",
    "archive_dir": ".merged",
    "backup_keep": 10,
    "timer_interval": "10min",
    "keepassxc_cli": "keepassxc-cli",
    "credential_name": "keepass-auto-merge.password",
}

SUPPORTED_MERGE_MODES = ("keep-newer",)
SUPPORTED_ON_MERGED = ("archive", "delete")


class ConfigError(Exception):
    """A configuration problem the operator has to fix."""


@dataclass(frozen=True)
class Config:
    watch_directory: Path
    master_filename: str = "keepass.kdbx"
    conflict_glob: str = "*sync-conflict*"
    merge_mode: str = "keep-newer"
    on_merged: str = "archive"
    archive_dir: str = ".merged"
    backup_keep: int = 10
    timer_interval: str = "10min"
    keepassxc_cli: str = "keepassxc-cli"
    credential_name: str = "keepass-auto-merge.password"
    source: Path | None = field(default=None, compare=False)

    @property
    def master_path(self) -> Path:
        return self.watch_directory / self.master_filename

    @property
    def archive_path(self) -> Path:
        return self.watch_directory / self.archive_dir


def load(path: Path | str) -> Config:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    return from_mapping(raw, source=path)


def from_mapping(raw: dict[str, Any], source: Path | None = None) -> Config:
    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise ConfigError(f"unknown key(s) in config: {', '.join(sorted(unknown))}")

    if not raw.get("watch_directory"):
        raise ConfigError("watch_directory is required (path to the folder holding the databases)")

    watch = Path(raw["watch_directory"]).expanduser()
    if not watch.is_dir():
        raise ConfigError(f"watch_directory does not exist or is not a directory: {watch}")

    merge_mode = raw.get("merge_mode", DEFAULTS["merge_mode"])
    if merge_mode not in SUPPORTED_MERGE_MODES:
        raise ConfigError(
            f"merge_mode {merge_mode!r} is not supported; this tool only merges non-destructively "
            f"(keep-newer), so deletions are never applied. Supported: "
            f"{', '.join(SUPPORTED_MERGE_MODES)}"
        )

    on_merged = raw.get("on_merged", DEFAULTS["on_merged"])
    if on_merged not in SUPPORTED_ON_MERGED:
        raise ConfigError(f"on_merged must be one of {', '.join(SUPPORTED_ON_MERGED)}")

    backup_keep = raw.get("backup_keep", DEFAULTS["backup_keep"])
    if not isinstance(backup_keep, int) or backup_keep < 0:
        raise ConfigError("backup_keep must be a non-negative integer")

    values = {**DEFAULTS, **raw}
    values.pop("watch_directory")
    return Config(watch_directory=watch, source=source, **values)
