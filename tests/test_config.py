"""Config loading: TOML parsing, defaults, and validation."""

from pathlib import Path

import pytest

from keepass_auto_merge.config import Config, ConfigError, load


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_minimal_config_uses_documented_defaults(tmp_path: Path) -> None:
    watch = tmp_path / "vaults"
    watch.mkdir()
    cfg = load(write_config(tmp_path, f'watch_directory = "{watch}"\n'))

    assert cfg.watch_directory == watch
    assert cfg.master_filename == "keepass.kdbx"
    assert cfg.conflict_glob == "*sync-conflict*"
    assert cfg.on_merged == "archive"
    assert cfg.archive_dir == ".merged"
    assert cfg.backup_keep == 10
    assert cfg.timer_interval == "10min"


def test_every_key_can_be_overridden(tmp_path: Path) -> None:
    watch = tmp_path / "vaults"
    watch.mkdir()
    cfg = load(
        write_config(
            tmp_path,
            f"""
watch_directory = "{watch}"
master_filename = "main.kdbx"
conflict_glob = "*conflicted*"
on_merged = "delete"
archive_dir = "done"
backup_keep = 3
timer_interval = "30min"
""",
        )
    )

    assert cfg.master_filename == "main.kdbx"
    assert cfg.conflict_glob == "*conflicted*"
    assert cfg.on_merged == "delete"
    assert cfg.archive_dir == "done"
    assert cfg.backup_keep == 3
    assert cfg.timer_interval == "30min"


def test_missing_config_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load(tmp_path / "nope.toml")


def test_invalid_toml_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="invalid TOML"):
        load(write_config(tmp_path, "watch_directory = [unclosed\n"))


def test_watch_directory_is_required(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="watch_directory"):
        load(write_config(tmp_path, "master_filename = 'x.kdbx'\n"))


def test_nonexistent_watch_directory_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="watch_directory"):
        load(write_config(tmp_path, f'watch_directory = "{tmp_path / "gone"}"\n'))


def test_unknown_key_is_an_error(tmp_path: Path) -> None:
    watch = tmp_path / "vaults"
    watch.mkdir()
    with pytest.raises(ConfigError, match="unknown key"):
        load(write_config(tmp_path, f'watch_directory = "{watch}"\nmaster_pasword = "oops"\n'))


def test_merge_mode_is_not_a_setting(tmp_path: Path) -> None:
    """There is only one merge behaviour: keep-newer. Configuring it was a lie."""
    watch = tmp_path / "vaults"
    watch.mkdir()
    with pytest.raises(ConfigError, match="unknown key"):
        load(write_config(tmp_path, f'watch_directory = "{watch}"\nmerge_mode = "keep-newer"\n'))


def test_keepassxc_cli_is_not_a_setting(tmp_path: Path) -> None:
    """There is no alternative engine to point at."""
    watch = tmp_path / "vaults"
    watch.mkdir()
    with pytest.raises(ConfigError, match="unknown key"):
        load(
            write_config(
                tmp_path,
                f'watch_directory = "{watch}"\nkeepassxc_cli = "/usr/bin/keepassxc-cli"\n',
            )
        )


def test_config_has_no_credential_attribute() -> None:
    names = set(Config.__annotations__)
    assert not any("password" in name or "secret" in name for name in names)


def test_master_path_is_inside_watch_directory(tmp_path: Path) -> None:
    watch = tmp_path / "vaults"
    watch.mkdir()
    cfg = load(write_config(tmp_path, f'watch_directory = "{watch}"\n'))
    assert cfg.master_path == watch / "keepass.kdbx"


def test_credential_name_has_a_default(tmp_path: Path) -> None:
    watch = tmp_path / "vaults"
    watch.mkdir()

    cfg = load(write_config(tmp_path, f'watch_directory = "{watch}"\n'))

    assert cfg.credential_name == "keepass-auto-merge.password"


def test_credential_name_can_be_overridden(tmp_path: Path) -> None:
    watch = tmp_path / "vaults"
    watch.mkdir()

    cfg = load(
        write_config(tmp_path, f'watch_directory = "{watch}"\ncredential_name = "kdbx.pw"\n')
    )

    assert cfg.credential_name == "kdbx.pw"
