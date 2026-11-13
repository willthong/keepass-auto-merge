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
