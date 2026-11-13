"""Debian packaging (#7): the .deb must carry the app, the units, and the conffile.

Built with `dpkg-deb` from a staged tree so the build works on any host with dpkg, including a
container without debhelper.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))

needs_dpkg = pytest.mark.skipif(
    shutil.which("dpkg-deb") is None, reason="dpkg-deb is not installed"
)


def project_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]


@needs_dpkg
def test_builds_a_deb_with_the_expected_version(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version=project_version(), dest=tmp_path)

    assert deb.name == f"keepass-auto-merge_{project_version()}_all.deb"
    assert deb.is_file()


@needs_dpkg
def test_deb_depends_on_keepassxc(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    fields = subprocess.run(
        ["dpkg-deb", "-f", str(deb), "Depends"], capture_output=True, text=True, check=True
    ).stdout

    assert "keepassxc" in fields
    assert "python3" in fields
    assert "python3-tomli-w" in fields


@needs_dpkg
def test_deb_installs_the_cli_units_and_config(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    contents = subprocess.run(
        ["dpkg-deb", "-c", str(deb)], capture_output=True, text=True, check=True
    ).stdout

    assert "usr/bin/keepass-auto-merge" in contents
    assert "keepass_auto_merge/cli.py" in contents
    assert "usr/lib/systemd/system/keepass-auto-merge.service" in contents
    assert "usr/lib/systemd/system/keepass-auto-merge.timer" in contents
    assert "etc/keepass-auto-merge/config.toml" in contents


@needs_dpkg
def test_config_is_a_conffile(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    conffiles = subprocess.run(
        ["dpkg-deb", "-I", str(deb), "conffiles"], capture_output=True, text=True, check=True
    ).stdout

    assert "/etc/keepass-auto-merge/config.toml" in conffiles


@needs_dpkg
def test_installing_enables_the_timer_and_path_unit(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    postinst = subprocess.run(
        ["dpkg-deb", "-I", str(deb), "postinst"], capture_output=True, text=True, check=True
    ).stdout

    assert "systemctl enable" in postinst
    assert "keepass-auto-merge.timer" in postinst
    assert "provision" in postinst


@needs_dpkg
def test_removal_disables_the_units(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    prerm = subprocess.run(
        ["dpkg-deb", "-I", str(deb), "prerm"], capture_output=True, text=True, check=True
    ).stdout

    assert "systemctl disable" in prerm


@needs_dpkg
def test_deb_creates_the_service_user(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    postinst = subprocess.run(
        ["dpkg-deb", "-I", str(deb), "postinst"], capture_output=True, text=True, check=True
    ).stdout

    assert "_keepass-merge" in postinst


def test_dpkg_buildpackage_entry_points_exist() -> None:
    rules = ROOT / "debian/rules"
    assert rules.is_file()
    assert rules.stat().st_mode & 0o111
    assert "packaging/build_deb.py" in rules.read_text(encoding="utf-8")


def test_control_declares_the_keepassxc_dependency() -> None:
    control = (ROOT / "debian/control").read_text(encoding="utf-8")

    assert "Package: keepass-auto-merge" in control
    assert "keepassxc" in control
    assert "Architecture: all" in control


def test_packaged_config_documents_the_credential_name() -> None:
    import build_deb

    assert "credential_name" in build_deb.CONFIG_TEMPLATE


@needs_dpkg
def test_shipped_service_loads_the_credential_provision_writes(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    unpacked = tmp_path / "unpacked"
    subprocess.run(["dpkg-deb", "-x", str(deb), str(unpacked)], check=True)
    service = (unpacked / "usr/lib/systemd/system/keepass-auto-merge.service").read_text(
        encoding="utf-8"
    )
    config = (unpacked / "etc/keepass-auto-merge/config.toml").read_text(encoding="utf-8")

    assert 'credential_name = "keepass-auto-merge.password"' in config
    assert "LoadCredential=keepass-auto-merge.password" in service


@needs_dpkg
def test_shipped_conffile_is_defaults_only_without_comments(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    unpacked = tmp_path / "unpacked"
    subprocess.run(["dpkg-deb", "-x", str(deb), str(unpacked)], check=True)

    config = (unpacked / "etc/keepass-auto-merge/config.toml").read_text(encoding="utf-8")

    assert "#" not in config
    assert "watch_directory" not in config
    assert "master_filename" in config
    assert "credential_name" in config


@needs_dpkg
def test_shipped_conffile_is_readable_by_the_service_user(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    listing = subprocess.run(
        ["dpkg-deb", "-c", str(deb)], capture_output=True, text=True, check=True
    ).stdout
    line = next(
        entry
        for entry in listing.splitlines()
        if entry.endswith("etc/keepass-auto-merge/config.toml")
    )

    assert line.startswith("-rw-r--r--")


@needs_dpkg
def test_postinst_tells_the_user_to_run_configure(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    postinst = subprocess.run(
        ["dpkg-deb", "-I", str(deb), "postinst"], capture_output=True, text=True, check=True
    ).stdout

    assert "keepass-auto-merge configure" in postinst
    assert "keepass-auto-merge provision" in postinst


@needs_dpkg
def test_prerm_is_silent_when_the_units_do_not_exist(tmp_path: Path) -> None:
    """Upgrading from a release that shipped no path unit must not spray errors."""
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    prerm = subprocess.run(
        ["dpkg-deb", "-I", str(deb), "prerm"], capture_output=True, text=True, check=True
    ).stdout
    script = tmp_path / "prerm"
    script.write_text(prerm, encoding="utf-8")
    script.chmod(0o755)

    stub = tmp_path / "bin"
    stub.mkdir()
    record = tmp_path / "calls.log"
    systemctl = stub / "systemctl"
    systemctl.write_text(
        f"""#!/bin/sh
echo "$@" >> {record}
echo "Failed to disable unit: Unit file keepass-auto-merge.path does not exist." >&2
exit 1
""",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    env = {**dict(__import__("os").environ), "PATH": f"{stub}:/usr/bin:/bin"}

    result = subprocess.run([str(script), "remove"], capture_output=True, text=True, env=env)

    calls = record.read_text(encoding="utf-8")
    assert "keepass-auto-merge.path" in calls
    assert "keepass-auto-merge.timer" in calls
    assert result.returncode == 0
    assert result.stderr == ""


@needs_dpkg
def test_prerm_succeeds_without_systemctl(tmp_path: Path) -> None:
    import build_deb

    deb = build_deb.build(version="1.2.3", dest=tmp_path)
    prerm = subprocess.run(
        ["dpkg-deb", "-I", str(deb), "prerm"], capture_output=True, text=True, check=True
    ).stdout
    script = tmp_path / "prerm"
    script.write_text(prerm, encoding="utf-8")
    script.chmod(0o755)
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    env = {"PATH": str(empty)}

    result = subprocess.run([str(script), "remove"], capture_output=True, text=True, env=env)

    assert result.returncode == 0
    assert result.stderr == ""
