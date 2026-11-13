#!/usr/bin/env python3
"""Build the Debian package from a staged tree, using nothing but dpkg-deb.

Run as `python3 packaging/build_deb.py [--dest DIR] [--version V]`. `debian/rules` calls it so
`dpkg-buildpackage` produces the same artefact as CI and as a developer's laptop.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tomli_w import dumps  # noqa: E402

from keepass_auto_merge import config  # noqa: E402

PACKAGE = "keepass-auto-merge"
SERVICE_USER = "_keepass-merge"
CONFIG_DIR = "etc/keepass-auto-merge"
UNIT_DIR = "usr/lib/systemd/system"

CONTROL = """\
Package: {package}
Version: {version}
Section: admin
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), keepassxc (>= 2.7), systemd
Maintainer: {maintainer}
Description: merge KeePass sync-conflict databases into one master KDBX
 Folds KeePass sync-conflict copies back into a single master database,
 non-destructively, on a systemd path unit and timer.
 .
 The merge uses keepassxc-cli, so history is preserved and deletions are never
 applied. The master is backed up before every run and replaced atomically.
"""

POSTINST = """\
#!/bin/sh
set -e

if ! getent group {user} >/dev/null; then
    addgroup --system {user}
fi
if ! getent passwd {user} >/dev/null; then
    adduser --system --ingroup {user} --no-create-home --home /nonexistent \\
        --shell /usr/sbin/nologin --gecos "KeePass auto-merge" {user}
fi

if [ -d /run/systemd/system ]; then
    systemctl daemon-reload || true
    systemctl enable keepass-auto-merge.timer || true
    systemctl restart keepass-auto-merge.timer || true
fi

cat <<'MESSAGE'

keepass-auto-merge is installed but not yet able to merge anything.

  1. Point the tool at the directory that holds the master database and the
     conflict files, and generate the units for it:
         sudo keepass-auto-merge configure --watch-directory /srv/vaults
     The {user} user needs read/write access to that directory.
  2. Store the master password:
         sudo keepass-auto-merge provision
  3. Prove it works:
         sudo keepass-auto-merge verify
  4. Check what the service will do:
         keepass-auto-merge check

MESSAGE
"""

PRERM = """\
#!/bin/sh
set -e

if [ -d /run/systemd/system ]; then
    systemctl disable keepass-auto-merge.path || true
    systemctl disable keepass-auto-merge.timer || true
    systemctl stop keepass-auto-merge.path || true
    systemctl stop keepass-auto-merge.timer || true
fi
"""

WRAPPER = """\
#!/usr/bin/python3
import sys

from keepass_auto_merge.cli import main

sys.exit(main())
"""


def config_template() -> str:
    """The packaged conffile: defaults only, no comments, no watch_directory (ADR-0004).

    A fresh install is explicitly unconfigured rather than pointing at a directory that does not
    exist; the README documents every key, and `configure` writes the real file.
    """
    return dumps(config.DEFAULT_VALUES)


CONFIG_TEMPLATE = config_template()


def project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def project_maintainer() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    author = data["project"]["authors"][0]
    return f"{author['name']} <{author['email']}>"


def build(version: str | None = None, dest: Path | None = None) -> Path:
    """Stage and package the .deb, returning its path."""
    version = version or project_version()
    dest = Path(dest or ROOT.parent)
    dest.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="deb-stage-") as tmp:
        stage = Path(tmp) / f"{PACKAGE}_{version}_all"
        _stage(stage, version)
        _write_md5sums(stage)
        deb = dest / f"{PACKAGE}_{version}_all.deb"
        subprocess.run(
            ["dpkg-deb", "--root-owner-group", "--build", str(stage), str(deb)],
            check=True,
            capture_output=True,
        )
    return deb


def _stage(stage: Path, version: str) -> None:
    _write(stage / f"usr/bin/{PACKAGE}", WRAPPER, mode=0o755)
    package_dir = stage / "usr/lib/python3/dist-packages/keepass_auto_merge"
    for source in sorted((ROOT / "src/keepass_auto_merge").glob("*.py")):
        shutil.copy2(source, _mkdir(package_dir) / source.name)

    _write(stage / CONFIG_DIR / "config.toml", CONFIG_TEMPLATE, mode=0o644)

    sys.path.insert(0, str(ROOT / "src"))
    from keepass_auto_merge.config import Config
    from keepass_auto_merge.units import PATH_UNIT, render

    rendered = render(Config(watch_directory=Path("/srv/vaults")))
    for name, content in rendered.items():
        _write(stage / UNIT_DIR / name, content, mode=0o644)
    # The path unit's watch directory is site-specific, so the package ships the service and
    # timer and the operator generates the path unit with `keepass-auto-merge units`.
    (stage / UNIT_DIR / PATH_UNIT).unlink(missing_ok=True)

    debian = _mkdir(stage / "DEBIAN")
    _write(
        debian / "control",
        CONTROL.format(package=PACKAGE, version=version, maintainer=project_maintainer()),
        mode=0o644,
    )
    _write(debian / "conffiles", f"/{CONFIG_DIR}/config.toml\n", mode=0o644)
    _write(debian / "postinst", POSTINST.format(user=SERVICE_USER), mode=0o755)
    _write(debian / "prerm", PRERM, mode=0o755)


def _write(path: Path, content: str, *, mode: int) -> None:
    _mkdir(path.parent)
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_md5sums(stage: Path) -> None:
    lines = []
    for path in sorted(stage.rglob("*")):
        if not path.is_file() or "DEBIAN" in path.relative_to(stage).parts:
            continue
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(stage)}")
    _write(stage / "DEBIAN/md5sums", "\n".join(lines) + "\n", mode=0o644)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=None)
    parser.add_argument("--dest", type=Path, default=None)
    args = parser.parse_args(argv)
    deb = build(version=args.version, dest=args.dest)
    print(deb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
