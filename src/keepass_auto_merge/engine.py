"""The merge engine: a thin, testable wrapper around the keepassxc-cli adapter (ADR-0001)."""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_CLI = "keepassxc-cli"


class EngineError(Exception):
    """keepassxc-cli could not do what we asked."""


def _run(argv: list[str], password: str, *, capture: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            argv,
            input=f"{password}\n",
            text=True,
            capture_output=capture,
            check=False,
        )
    except FileNotFoundError as exc:
        raise EngineError(f"merge engine not found: {argv[0]}") from exc


def unlock_check(master: object, password: str, *, cli: str = DEFAULT_CLI) -> None:
    """Prove the credential unlocks the database, without printing decrypted content."""
    result = _run([cli, "export", "-q", "-f", "xml", str(master)], password)
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else f"exit {result.returncode}"
        raise EngineError(f"credential does not unlock {master}: {reason}")


def export_xml(path: object, password: str, *, cli: str = DEFAULT_CLI) -> str:
    """Decrypt a database to KeePass XML in memory; never printed, never written."""
    result = _run([cli, "export", "-q", "-f", "xml", str(path)], password)
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else f"exit {result.returncode}"
        raise EngineError(f"cannot read {Path(path).name}: {reason}")
    return result.stdout


def merge_into(target: object, conflict: object, password: str, *, cli: str = DEFAULT_CLI) -> str:
    """Merge `conflict` into `target` in place, with one password for both databases."""
    result = _run(
        [cli, "merge", "-s", str(target), str(conflict)],
        password,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else f"exit {result.returncode}"
        raise EngineError(f"merge failed for {Path(conflict).name}: {reason}")
    return result.stdout
