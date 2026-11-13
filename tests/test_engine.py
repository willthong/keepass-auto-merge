"""The keepassxc-cli adapter: it must not hide the engine's own diagnosis."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from keepass_auto_merge import engine


def test_unlock_failure_surfaces_the_engine_message(stub_bin: Path, monkeypatch) -> None:
    script = stub_bin / "keepassxc-cli"
    # Mimic KeePassXC: with -q it says nothing, without it it explains the failure.
    script.write_text(
        '#!/bin/sh\nfor a in "$@"; do [ "$a" = "-q" ] && exit 1; done\n'
        'echo "Invalid credentials were provided" >&2\nexit 1\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ['PATH']}")

    with pytest.raises(engine.EngineError) as raised:
        engine.unlock_check(Path("/tmp/x.kdbx"), "pw")

    assert "Invalid credentials were provided" in str(raised.value)
