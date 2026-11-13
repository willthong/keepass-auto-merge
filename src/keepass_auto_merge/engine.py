"""The merge engine: a thin, testable wrapper around the keepassxc-cli adapter (ADR-0001)."""

from __future__ import annotations

import subprocess

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
