"""The `configure` verb from the command line (#9): flags, prompts, units, systemd."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from keepass_auto_merge import cli
from keepass_auto_merge import config as config_module
from keepass_auto_merge.config import load


def watch_dir(tmp_path: Path) -> Path:
    path = tmp_path / "vaults"
    path.mkdir()
    return path


def config_file(tmp_path: Path) -> Path:
    return tmp_path / "config.toml"


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_configure_with_flags_needs_no_tty(tmp_path: Path, capsys) -> None:
    watch = watch_dir(tmp_path)

    code, out, _ = run(
        capsys, "configure", "--config", str(config_file(tmp_path)), "--watch-directory", str(watch)
    )

    assert code == 0
    assert load(config_file(tmp_path)).watch_directory == watch
    assert str(config_file(tmp_path)) in out


def test_configure_sets_any_key(tmp_path: Path, capsys) -> None:
    watch = watch_dir(tmp_path)

    code, _, _ = run(
        capsys,
        "configure",
        "--config",
        str(config_file(tmp_path)),
        "--watch-directory",
        str(watch),
        "--backup-keep",
        "3",
        "--on-merged",
        "delete",
    )

    cfg = load(config_file(tmp_path))
    assert code == 0
    assert cfg.backup_keep == 3
    assert cfg.on_merged == "delete"


def test_bare_configure_without_a_tty_is_a_usage_error(tmp_path: Path, capsys) -> None:
    code, _, err = run(capsys, "configure", "--config", str(config_file(tmp_path)))

    assert code == 2
    assert "--watch-directory" in err


def test_configure_refuses_a_missing_watch_directory(tmp_path: Path, capsys) -> None:
    code, _, err = run(
        capsys,
        "configure",
        "--config",
        str(config_file(tmp_path)),
        "--watch-directory",
        str(tmp_path / "gone"),
    )

    assert code == 1
    assert "watch_directory" in err
    assert not config_file(tmp_path).exists()


def test_interactive_configure_explains_every_setting(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch = watch_dir(tmp_path)
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    answers = iter([str(watch), "y"])

    def fake_input(prompt: str = "") -> str:
        print(prompt, end="")
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)

    code, out, _ = run(capsys, "configure", "--config", str(config_file(tmp_path)))

    assert code == 0
    for setting in config_module.SETTINGS:
        assert setting.description in out, f"{setting.name} was not explained"
        assert setting.flag in out
    assert load(config_file(tmp_path)).watch_directory == watch


def test_interactive_configure_can_be_declined(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch = watch_dir(tmp_path)
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    answers = iter([str(watch), "n"])

    def fake_input(prompt: str = "") -> str:
        print(prompt, end="")
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)

    code, out, _ = run(capsys, "configure", "--config", str(config_file(tmp_path)))

    assert code == 1
    assert "aborted" in out.lower()
    assert not config_file(tmp_path).exists()


def test_interactive_configure_prefills_existing_values(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch = watch_dir(tmp_path)
    path = config_file(tmp_path)
    cli.main(
        ["configure", "--config", str(path), "--watch-directory", str(watch), "--backup-keep", "2"]
    )
    capsys.readouterr()

    monkeypatch.setattr(cli, "_interactive", lambda: True)
    monkeypatch.setattr(cli, "_interactive_answers", lambda *_: {"watch_directory": str(watch)})
    code, out, _ = run(capsys, "configure", "--config", str(path))

    assert code == 0
    assert "2" in out
    assert load(path).backup_keep == 2


def test_configure_regenerates_units_for_the_watch_directory(tmp_path: Path, capsys) -> None:
    watch = watch_dir(tmp_path)
    units_dir = tmp_path / "units"

    code, _, _ = run(
        capsys,
        "configure",
        "--config",
        str(config_file(tmp_path)),
        "--watch-directory",
        str(watch),
        "--units-dir",
        str(units_dir),
    )

    assert code == 0
    assert (units_dir / "keepass-auto-merge.path").is_file()
    assert str(watch) in (units_dir / "keepass-auto-merge.path").read_text(encoding="utf-8")


def test_configure_applies_the_units_when_systemd_is_present(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch, stub_bin: Path
) -> None:
    watch = watch_dir(tmp_path)
    record = tmp_path / "systemctl.log"
    script = stub_bin / "systemctl"
    script.write_text(f'#!/bin/sh\necho "$@" >> {record}\n', encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(cli, "_systemd_available", lambda: True)

    code, _, _ = run(
        capsys,
        "configure",
        "--config",
        str(config_file(tmp_path)),
        "--watch-directory",
        str(watch),
        "--units-dir",
        str(tmp_path / "units"),
    )

    calls = record.read_text(encoding="utf-8")
    assert code == 0
    assert "daemon-reload" in calls
    assert "enable" in calls
    assert "keepass-auto-merge.timer" in calls


def test_configure_prints_the_commands_when_systemd_is_absent(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch = watch_dir(tmp_path)
    monkeypatch.setattr(cli, "_systemd_available", lambda: False)

    _, out, _ = run(
        capsys,
        "configure",
        "--config",
        str(config_file(tmp_path)),
        "--watch-directory",
        str(watch),
        "--units-dir",
        str(tmp_path / "units"),
    )

    assert "systemctl daemon-reload" in out


def test_check_reports_every_effective_setting(tmp_path: Path, capsys) -> None:
    watch = watch_dir(tmp_path)
    (watch / "keepass.kdbx").write_bytes(b"master")
    path = config_file(tmp_path)
    cli.main(["configure", "--config", str(path), "--watch-directory", str(watch)])
    capsys.readouterr()

    code, out, _ = run(capsys, "check", "--config", str(path))

    assert code == 0
    assert str(path) in out
    for setting in config_module.SETTINGS:
        assert setting.name in out
