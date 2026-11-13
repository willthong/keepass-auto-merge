"""systemd units (#6): generated from config, least privilege, and safe to run concurrently."""

from __future__ import annotations

import fcntl
import shutil
from pathlib import Path

import pytest
from conftest import PASSWORD, add_entry, create_db, needs_keepassxc

from keepass_auto_merge import cli, merge, units
from keepass_auto_merge.config import Config

pytestmark = pytest.mark.skipif(
    shutil.which("keepassxc-cli") is None, reason="keepassxc-cli is not installed"
)


def config(watch: Path, **overrides: object) -> Config:
    return Config(watch_directory=watch, **overrides)


def test_renders_three_units(tmp_path: Path) -> None:
    rendered = units.render(config(tmp_path))

    assert set(rendered) == {
        "keepass-auto-merge.service",
        "keepass-auto-merge.path",
        "keepass-auto-merge.timer",
    }


def test_service_runs_the_merge_as_the_service_user(tmp_path: Path) -> None:
    service = units.render(config(tmp_path))["keepass-auto-merge.service"]

    assert "Type=oneshot" in service
    assert "User=_keepass-merge" in service
    assert "Group=_keepass-merge" in service
    assert "ExecStart=" in service
    assert " run" in service


def test_service_receives_the_credential_from_systemd(tmp_path: Path) -> None:
    service = units.render(config(tmp_path))["keepass-auto-merge.service"]

    assert "LoadCredential=keepass-auto-merge.password" in service


def test_path_unit_watches_the_configured_directory(tmp_path: Path) -> None:
    path_unit = units.render(config(tmp_path))["keepass-auto-merge.path"]

    assert f"PathExistsGlob={tmp_path}/*sync-conflict*" in path_unit
    assert "Unit=keepass-auto-merge.service" in path_unit
    assert "WantedBy=multi-user.target" in path_unit


def test_path_unit_follows_a_custom_glob(tmp_path: Path) -> None:
    path_unit = units.render(config(tmp_path, conflict_glob="*copy*"))["keepass-auto-merge.path"]

    assert f"PathExistsGlob={tmp_path}/*copy*" in path_unit


def test_timer_fires_every_ten_minutes_by_default(tmp_path: Path) -> None:
    timer = units.render(config(tmp_path))["keepass-auto-merge.timer"]

    assert "OnUnitActiveSec=10min" in timer
    assert "OnBootSec=5min" in timer
    assert "Unit=keepass-auto-merge.service" in timer


def test_timer_honours_the_configured_interval(tmp_path: Path) -> None:
    timer = units.render(config(tmp_path, timer_interval="30min"))["keepass-auto-merge.timer"]

    assert "OnUnitActiveSec=30min" in timer


def test_units_pass_systemd_analyze_verify(tmp_path: Path, tmp_path_factory) -> None:
    if shutil.which("systemd-analyze") is None or shutil.which("systemd") is None:
        pytest.skip("systemd tooling is not installed")

    import subprocess

    directory = tmp_path_factory.mktemp("units")
    for name, content in units.render(config(tmp_path)).items():
        (directory / name).write_text(content, encoding="utf-8")
    result = subprocess.run(
        ["systemd-analyze", "verify", "--man=no", *sorted(directory.iterdir())],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@needs_keepassxc
def test_overlapping_runs_do_not_merge_twice(tmp_path: Path, capsys) -> None:
    watch = tmp_path / "vaults"
    watch.mkdir()
    master = create_db(watch / "keepass.kdbx")
    add_entry(master, "base")
    import shutil

    conflict = Path(shutil.copy2(master, watch / "keepass.sync-conflict-a.kdbx"))
    add_entry(conflict, "a")

    with open(watch / merge.LOCK_NAME, "w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        code = cli.main(
            [
                "run",
                "--config",
                str(_config_file(tmp_path, watch)),
                "--credential-file",
                str(_credential_file(tmp_path)),
            ]
        )
        captured = capsys.readouterr()

    assert code == 0
    assert "in progress" in (captured.out + captured.err).lower()
    assert conflict.exists()


def _config_file(tmp_path: Path, watch: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(f'watch_directory = "{watch}"\n', encoding="utf-8")
    return path


def _credential_file(tmp_path: Path) -> Path:
    path = tmp_path / "cred"
    path.write_text(PASSWORD, encoding="utf-8")
    return path
