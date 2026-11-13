"""Provisioning and verifying the stored credential (#2).

The credential is the master password shared by every database. It must never appear in argv,
the environment, or a config file: `provision` takes it on stdin, and `verify` proves it unlocks
the master database.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from conftest import create_db, needs_keepassxc

from keepass_auto_merge import cli

PASSWORD = "correct horse battery staple"


def run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, str, str]:
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def fake_systemd_creds(stub_bin: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in for `systemd-creds encrypt` that stores what it read on stdin."""
    script = stub_bin / "systemd-creds"
    script.write_text(
        """#!/bin/sh
# only understand: encrypt --name=<n> <outfile>
out=""
name=""
for arg in "$@"; do
  case "$arg" in
    --name=*) name="${arg#--name=}" ;;
    --name) shift ;;
    /dev/stdin|-|-) ;;
    encrypt|--*) ;;
    *) out="$arg" ;;
  esac
done
if [ -z "$out" ]; then echo "stub: no output file" >&2; exit 1; fi
cat > "$out"
echo "name=$name" >&2
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ['PATH']}")
    return script


@pytest.fixture
def fake_keepassxc(stub_bin: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in for keepassxc-cli that accepts exactly one password."""
    script = stub_bin / "keepassxc-cli"
    script.write_text(
        """#!/bin/sh
read -r given
if [ "$given" = "correct horse battery staple" ]; then
  echo "<KeePassFile/>"
  exit 0
fi
echo "Invalid credentials were provided" >&2
exit 1
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ['PATH']}")
    return script


def test_provision_stores_the_password_from_stdin(
    fake_systemd_creds: Path, tmp_path: Path, capsys, monkeypatch
) -> None:
    dest = tmp_path / "credstore" / "keepass-auto-merge.password"
    dest.parent.mkdir()
    monkeypatch.setattr("sys.stdin", _stdin(f"{PASSWORD}\n"))

    code, out, _ = run(capsys, ["provision", "--dest", str(dest)])

    assert code == 0
    assert dest.read_text(encoding="utf-8") == PASSWORD
    assert PASSWORD not in out


def test_provision_never_passes_the_password_in_argv(
    stub_bin: Path, tmp_path: Path, capsys, monkeypatch
) -> None:
    recorded = tmp_path / "argv.txt"
    script = stub_bin / "systemd-creds"
    script.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" > {recorded}\ncat > /dev/null\n', encoding="utf-8"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr("sys.stdin", _stdin(f"{PASSWORD}\n"))
    dest = tmp_path / "cred"

    run(capsys, ["provision", "--dest", str(dest)])

    assert PASSWORD not in recorded.read_text(encoding="utf-8")


def test_provision_rejects_an_empty_password(
    fake_systemd_creds: Path, tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setattr("sys.stdin", _stdin("\n"))

    code, _, err = run(capsys, ["provision", "--dest", str(tmp_path / "cred")])

    assert code == 1
    assert "empty" in err.lower()
    assert not (tmp_path / "cred").exists()


def test_provision_reports_where_it_wrote_the_credential(
    fake_systemd_creds: Path, tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setattr("sys.stdin", _stdin(f"{PASSWORD}\n"))
    dest = tmp_path / "cred"

    _, out, _ = run(capsys, ["provision", "--dest", str(dest)])

    assert str(dest) in out
    assert "keepass-auto-merge.password" in out


def test_verify_succeeds_when_the_credential_unlocks_the_master(
    fake_keepassxc: Path, tmp_path: Path, capsys
) -> None:
    master = tmp_path / "keepass.kdbx"
    master.write_bytes(b"not really a kdbx")
    credential = tmp_path / "cred"
    credential.write_text(PASSWORD, encoding="utf-8")

    code, out, _ = run(
        capsys, ["verify", "--credential-file", str(credential), "--master", str(master)]
    )

    assert code == 0
    assert "unlocks" in out.lower()


def test_verify_fails_with_a_clear_message_for_a_wrong_password(
    fake_keepassxc: Path, tmp_path: Path, capsys
) -> None:
    master = tmp_path / "keepass.kdbx"
    master.write_bytes(b"not really a kdbx")
    credential = tmp_path / "cred"
    credential.write_text("wrong", encoding="utf-8")

    code, _, err = run(
        capsys, ["verify", "--credential-file", str(credential), "--master", str(master)]
    )

    assert code == 1
    assert "does not unlock" in err.lower()


def test_verify_never_prints_decrypted_content(
    fake_keepassxc: Path, tmp_path: Path, capsys
) -> None:
    master = tmp_path / "keepass.kdbx"
    master.write_bytes(b"x")
    credential = tmp_path / "cred"
    credential.write_text(PASSWORD, encoding="utf-8")

    _, out, _ = run(
        capsys, ["verify", "--credential-file", str(credential), "--master", str(master)]
    )

    assert "<KeePassFile/>" not in out


def test_missing_credential_file_is_an_error(tmp_path: Path, capsys) -> None:
    master = tmp_path / "keepass.kdbx"
    master.write_bytes(b"x")

    code, _, err = run(
        capsys, ["verify", "--credential-file", str(tmp_path / "gone"), "--master", str(master)]
    )

    assert code == 1
    assert "credential" in err.lower()


class _stdin:
    """Minimal stdin stand-in so tests never touch a TTY."""

    def __init__(self, text: str) -> None:
        self._text = text

    def read(self, *_args: object) -> str:
        return self._text

    def isatty(self) -> bool:
        return False


def test_provision_pipes_to_the_real_systemd_creds_when_available(tmp_path: Path) -> None:
    if not _have("systemd-creds"):
        pytest.skip("systemd-creds is not installed")
    from keepass_auto_merge import credential

    dest = tmp_path / "cred"
    try:
        credential.provision(PASSWORD, dest)
    except credential.CredentialError as exc:  # e.g. no host secret in a container
        pytest.skip(f"systemd-creds cannot encrypt here: {exc}")
    decrypted = subprocess.run(
        ["systemd-creds", "decrypt", str(dest), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert decrypted.stdout == PASSWORD


def _have(binary: str) -> bool:
    from shutil import which

    return which(binary) is not None


@needs_keepassxc
def test_verify_with_the_real_engine_accepts_the_right_password(tmp_path: Path, capsys) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    credential = tmp_path / "cred"
    credential.write_text(PASSWORD, encoding="utf-8")

    code, out, _ = run(
        capsys, ["verify", "--credential-file", str(credential), "--master", str(master)]
    )

    assert code == 0
    assert "unlocks" in out.lower()


@needs_keepassxc
def test_verify_with_the_real_engine_rejects_a_wrong_password(tmp_path: Path, capsys) -> None:
    master = create_db(tmp_path / "keepass.kdbx")
    credential = tmp_path / "cred"
    credential.write_text("not it", encoding="utf-8")

    code, _, err = run(
        capsys, ["verify", "--credential-file", str(credential), "--master", str(master)]
    )

    assert code == 1
    assert "does not unlock" in err.lower()


def test_provision_ignores_credentials_directory_for_its_destination(
    tmp_path: Path, monkeypatch
) -> None:
    """Provisioning must never target systemd's read-only $CREDENTIALS_DIRECTORY."""
    from keepass_auto_merge import credential

    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path / "readonly"))

    assert credential.provision_path() == Path(
        "/etc/credstore.encrypted/keepass-auto-merge.password"
    )


def test_provision_defaults_to_the_name_the_unit_loads(
    fake_systemd_creds: Path, tmp_path: Path, capsys, monkeypatch
) -> None:
    watch = tmp_path / "vaults"
    watch.mkdir()
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        f'watch_directory = "{watch}"\ncredential_name = "from-config.pw"\n', encoding="utf-8"
    )
    monkeypatch.setattr("sys.stdin", _stdin(f"{PASSWORD}\n"))
    dest = tmp_path / "cred"

    code, out, _ = run(capsys, ["provision", "--config", str(config_file), "--dest", str(dest)])

    assert code == 0
    assert "from-config.pw" in out


def test_run_reads_the_configured_credential_name(tmp_path: Path, monkeypatch, capsys) -> None:
    from keepass_auto_merge import credential

    directory = tmp_path / "creds"
    directory.mkdir()
    (directory / "site.pw").write_text(PASSWORD, encoding="utf-8")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(directory))

    assert credential.default_path("site.pw") == directory / "site.pw"
