"""`configure` applying settings: validation, atomic rewrite, repair (#9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from keepass_auto_merge import config as config_module
from keepass_auto_merge import configure
from keepass_auto_merge.config import ConfigError, load


def watch_dir(tmp_path: Path) -> Path:
    path = tmp_path / "vaults"
    path.mkdir()
    return path


def test_writes_every_key_without_comments(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    watch = watch_dir(tmp_path)

    configure.apply(path, {"watch_directory": str(watch)})

    written = path.read_text(encoding="utf-8")
    assert "#" not in written
    cfg = load(path)
    assert cfg.watch_directory == watch
    assert cfg.master_filename == "keepass.kdbx"
    assert cfg.backup_keep == 10
    assert cfg.credential_name == "keepass-auto-merge.password"


def test_written_file_is_readable_by_the_service_user(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    configure.apply(path, {"watch_directory": str(watch_dir(tmp_path))})

    assert path.stat().st_mode & 0o777 == 0o644


def test_refuses_a_watch_directory_that_does_not_exist(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    missing = tmp_path / "gone"

    with pytest.raises(ConfigError, match="watch_directory"):
        configure.apply(path, {"watch_directory": str(missing)})

    assert not path.exists()


def test_refuses_and_leaves_the_file_untouched(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        f'watch_directory = "{tmp_path}/vaults"\nkeepassxc_cli = "old"\n', encoding="utf-8"
    )
    before = path.read_bytes()

    with pytest.raises(ConfigError):
        configure.apply(path, {"on_merged": "nonsense"})

    assert path.read_bytes() == before


def test_preserves_values_it_is_not_overriding(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    watch = watch_dir(tmp_path)
    configure.apply(path, {"watch_directory": str(watch), "backup_keep": 3})

    configure.apply(path, {"watch_directory": str(watch)})

    assert load(path).backup_keep == 3


def test_repairs_a_file_with_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    watch = watch_dir(tmp_path)
    path.write_text(f'watch_directory = "{watch}"\nmaster_pasword = "typo"\n', encoding="utf-8")

    configure.apply(path, {})

    assert "master_pasword" not in path.read_text(encoding="utf-8")
    load(path)


def test_creates_the_file_when_absent(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "config.toml"

    configure.apply(path, {"watch_directory": str(watch_dir(tmp_path))})

    assert path.is_file()


def test_write_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.toml"
    watch = watch_dir(tmp_path)
    configure.apply(path, {"watch_directory": str(watch)})
    before = path.read_bytes()

    def explode(*args: object, **kwargs: object) -> str:
        raise OSError("disk on fire")

    monkeypatch.setattr(config_module, "dumps", explode)

    with pytest.raises(OSError):
        configure.apply(path, {"backup_keep": 1})

    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".config")] == []


def test_rejects_an_unsupported_merge_mode(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    with pytest.raises(ConfigError, match="merge_mode"):
        configure.apply(
            path, {"watch_directory": str(watch_dir(tmp_path)), "merge_mode": "synchronize"}
        )
