"""Configuration: a single TOML file describing the watch directory and merge behaviour.

The master password is deliberately absent: it lives in the system credential store (ADR-0002).
"""

from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tomli_w import dumps

DEFAULT_VALUES_PLACEHOLDER: dict[str, Any] = {
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


class NotConfigured(ConfigError):
    """A setting the tool cannot invent is missing, so nothing can run."""


@dataclass(frozen=True)
class Setting:
    """One configuration key: default, command-line spelling, and what it means."""

    name: str
    default: Any
    description: str
    flag: str
    kind: type = str


SETTINGS: tuple[Setting, ...] = (
    Setting(
        "watch_directory",
        None,
        "Directory holding the master database and the conflict files.",
        "--watch-directory",
    ),
    Setting(
        "master_filename",
        "keepass.kdbx",
        "The authoritative database that every conflict file is merged into.",
        "--master-filename",
    ),
    Setting(
        "conflict_glob",
        "*sync-conflict*",
        "Case-insensitive glob for the files to merge (e.g. *sync-conflict*).",
        "--conflict-glob",
    ),
    Setting(
        "merge_mode",
        "keep-newer",
        "How entries are reconciled. Only keep-newer is supported: deletions are never applied.",
        "--merge-mode",
    ),
    Setting(
        "on_merged",
        "archive",
        "What happens to a conflict file after merging it: archive or delete.",
        "--on-merged",
    ),
    Setting(
        "archive_dir",
        ".merged",
        "Subdirectory of the watch directory where merged conflict files are kept.",
        "--archive-dir",
    ),
    Setting(
        "backup_keep",
        10,
        "How many hidden timestamped backups of the master to keep. 0 disables backups.",
        "--backup-keep",
        kind=int,
    ),
    Setting(
        "timer_interval",
        "10min",
        "How often the timer re-scans, on top of the path unit's watch.",
        "--timer-interval",
    ),
    Setting(
        "keepassxc_cli",
        "keepassxc-cli",
        "Path to the keepassxc-cli merge engine.",
        "--keepassxc-cli",
    ),
    Setting(
        "credential_name",
        "keepass-auto-merge.password",
        "Name of the credential in the system credential store (must match provision/units).",
        "--credential-name",
    ),
)


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


UNCONFIGURED_HINT = "run 'keepass-auto-merge configure'"


def load(path: Path | str) -> Config:
    path = Path(path)
    if not path.is_file():
        raise NotConfigured(f"not configured: config file not found: {path}. {UNCONFIGURED_HINT}")
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
        raise NotConfigured(f"not configured: watch_directory is not set. {UNCONFIGURED_HINT}")

    watch = Path(raw["watch_directory"]).expanduser()
    if not watch.is_dir():
        raise NotConfigured(
            "not configured: watch_directory is not an existing directory: "
            f"{watch}. {UNCONFIGURED_HINT}"
        )

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


def read_permissive(path: Path) -> dict[str, Any]:
    """Read a config file, ignoring keys this version does not know about.

    `configure` is the repair verb, so it must not be blocked by a file it is meant to fix.
    """
    if not path.is_file():
        return {}
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    return {key: value for key, value in raw.items() if key in DEFAULTS}


def write(path: Path, values: dict[str, Any]) -> None:
    """Write the whole config atomically, in setting order, with no comments (ADR-0004)."""
    ordered = {
        setting.name: values[setting.name]
        for setting in SETTINGS
        if setting.name in values and values[setting.name] is not None
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dumps(ordered)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


DEFAULTS = {setting.name: setting.default for setting in SETTINGS}
DEFAULT_VALUES = {key: value for key, value in DEFAULTS.items() if key != "watch_directory"}
