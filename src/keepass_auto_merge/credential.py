"""The credential: the one master password shared by every database.

The password is encrypted with `systemd-creds` into the system credential store and reaches the
service through `LoadCredential=` (ADR-0002). It is never passed in argv, the environment, or the
config file: every hand-off goes through stdin or a file read.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_NAME = "keepass-auto-merge.password"
DEFAULT_CREDSTORE = Path("/etc/credstore.encrypted")


class CredentialError(Exception):
    """The credential could not be stored, read, or does not unlock the database."""


def provision(password: str, dest: Path, *, name: str = DEFAULT_NAME) -> None:
    """Encrypt `password` into `dest` using systemd-creds, reading it from stdin."""
    if not password:
        raise CredentialError("refusing to store an empty password")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["systemd-creds", "encrypt", f"--name={name}", "-", str(dest)],
            input=password,
            text=True,
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise CredentialError("systemd-creds not found; install systemd") from exc
    except subprocess.CalledProcessError as exc:
        raise CredentialError(
            f"systemd-creds failed: {exc.stderr.strip() or exc.returncode}"
        ) from exc


def read(path: Path) -> str:
    """Read a decrypted credential file, as exposed by systemd's LoadCredential."""
    try:
        value = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CredentialError(f"credential not found: {path}") from exc
    except OSError as exc:
        raise CredentialError(f"cannot read credential {path}: {exc}") from exc
    password = value.rstrip("\n")
    if not password:
        raise CredentialError(f"credential is empty: {path}")
    return password


def decrypt(path: Path, name: str = DEFAULT_NAME) -> str:
    """Decrypt a credential stored by `systemd-creds encrypt`, for use outside a unit."""
    try:
        result = subprocess.run(
            ["systemd-creds", "decrypt", f"--name={name}", str(path), "-"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise CredentialError("systemd-creds not found; install systemd") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or f"exit {exc.returncode}"
        raise CredentialError(f"cannot decrypt credential {path}: {detail}") from exc
    password = result.stdout.rstrip("\n")
    if not password:
        raise CredentialError(f"decrypted credential is empty: {path}")
    return password


def load(explicit_path: Path | None = None, name: str = DEFAULT_NAME) -> str:
    """The master password, wherever it happens to live.

    Under systemd, LoadCredential has already decrypted it into $CREDENTIALS_DIRECTORY. Outside a
    unit the file on disk is still ciphertext, so it has to be decrypted explicitly; reading it as
    text would feed the ciphertext to the merge engine and look like a wrong password.
    """
    if explicit_path is not None:
        return read(Path(explicit_path))
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if directory:
        return read(Path(directory) / name)
    return decrypt(DEFAULT_CREDSTORE / name, name)


def default_path(name: str = DEFAULT_NAME) -> Path:
    """Where the running service reads the credential from."""
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if directory:
        return Path(directory) / name
    return DEFAULT_CREDSTORE / name


def provision_path(name: str = DEFAULT_NAME) -> Path:
    """Where `provision` writes the credential.

    Deliberately ignores $CREDENTIALS_DIRECTORY: inside a unit that directory is a read-only
    tmpfs that only systemd populates, so writing there would fail.
    """
    return DEFAULT_CREDSTORE / name


def prompt_password(stream: object = None) -> str:
    """Read the password from stdin, never echoing it and never requiring a TTY."""
    stream = stream or sys.stdin
    if hasattr(stream, "isatty") and stream.isatty():
        import getpass

        password = getpass.getpass("Master password: ")
        if getpass.getpass("Repeat: ") != password:
            raise CredentialError("passwords did not match")
        return password
    return stream.read().rstrip("\n")
