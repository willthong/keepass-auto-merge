"""Shared fixtures: a real KeePassXC database factory and stub binaries."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PASSWORD = "correct horse battery staple"

needs_keepassxc = pytest.mark.skipif(
    shutil.which("keepassxc-cli") is None, reason="keepassxc-cli is not installed"
)


def create_db(path: Path, password: str = PASSWORD) -> Path:
    """Create an empty KDBX database using the real KeePassXC CLI."""
    subprocess.run(
        ["keepassxc-cli", "db-create", "-q", "-p", str(path)],
        input=f"{password}\n{password}\n",
        text=True,
        check=True,
        capture_output=True,
    )
    return path


def add_entry(path: Path, title: str, username: str = "user", password: str = PASSWORD) -> None:
    subprocess.run(
        ["keepassxc-cli", "add", "-q", "-p", str(path), title, "-u", username],
        input=f"{password}\n{password}\nsecret\n",
        text=True,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def stub_bin(tmp_path: Path) -> Path:
    """A directory to put fake executables in, prepended to PATH by tests."""
    directory = tmp_path / "stub-bin"
    directory.mkdir()
    return directory


def _run_cli(args: list[str], password: str) -> str:
    result = subprocess.run(
        ["keepassxc-cli", *args], input=f"{password}\n", text=True, capture_output=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"keepassxc-cli {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def list_entries(path: Path, password: str = PASSWORD) -> list[str]:
    """Relative paths of every entry in the database, skipping the recycle bin."""
    out = _run_cli(["ls", "-q", "-R", str(path)], password)
    return sorted(line.strip() for line in out.splitlines() if line.strip())


def entry_password(path: Path, title: str, password: str = PASSWORD) -> str:
    return _run_cli(["show", "-q", "-a", "Password", str(path), title], password).strip()


def set_entry_password(path: Path, title: str, new_value: str, password: str = PASSWORD) -> None:
    """Change an entry's password, which bumps its modification time."""
    subprocess.run(
        ["keepassxc-cli", "edit", "-q", "-p", str(path), title],
        input=f"{password}\n{new_value}\n{new_value}\n",
        text=True,
        check=True,
        capture_output=True,
    )


def archive_of(path: Path, name: str) -> Path:
    directory = path / name
    directory.mkdir(exist_ok=True)
    return directory
