"""Command line entry point.

Exit codes are part of the contract: 0 success, 1 failure, 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, credential
from .config import Config, ConfigError, load
from .discovery import DiscoveryError, discover
from .engine import EngineError, unlock_check

DEFAULT_CONFIG = Path("/etc/keepass-auto-merge/config.toml")

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


VERSION_STRING = f"keepass-auto-merge {__version__}"


def _options() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"path to the TOML config (default: {DEFAULT_CONFIG})",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keepass-auto-merge",
        description=(
            "Merge KeePass sync-conflict databases into one master KDBX, non-destructively."
        ),
    )
    parser.add_argument("--version", action="version", version=VERSION_STRING)
    sub = parser.add_subparsers(dest="command", metavar="command")
    common = _options()

    check_cmd = sub.add_parser(
        "check", parents=[common], help="report the merge plan without changing anything"
    )
    check_cmd.add_argument("--version", action="version", version=VERSION_STRING)
    run_cmd = sub.add_parser(
        "run", parents=[common], help="merge every conflict file into the master database"
    )
    run_cmd.add_argument("--version", action="version", version=VERSION_STRING)
    run_cmd.add_argument(
        "--dry-run", action="store_true", help="report what would happen without writing anything"
    )

    provision_cmd = sub.add_parser(
        "provision",
        parents=[common],
        help="encrypt the master password into the system credential store (reads stdin)",
    )
    provision_cmd.add_argument("--dest", type=Path, default=credential.default_path())
    provision_cmd.add_argument("--name", default=credential.DEFAULT_NAME)

    verify_cmd = sub.add_parser(
        "verify",
        parents=[common],
        help="prove the stored credential unlocks the master database",
    )
    verify_cmd.add_argument("--credential-file", type=Path, default=None)
    verify_cmd.add_argument("--master", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:  # --version and argparse usage errors
        return int(exc.code or 0)
    if not args.command:
        parser.print_usage(sys.stderr)
        return EXIT_USAGE

    try:
        if args.command == "provision":
            return provision_command(args)
        if args.command == "verify":
            return verify_command(args)

        config = load(args.config)
        if args.command == "check":
            return check(config)
    except (ConfigError, DiscoveryError, credential.CredentialError, EngineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    print(f"error: unknown command {args.command}", file=sys.stderr)
    return EXIT_USAGE


def provision_command(args: argparse.Namespace) -> int:
    password = credential.prompt_password()
    credential.provision(password, args.dest, name=args.name)
    print(f"credential written to {args.dest}")
    print(f"name: {args.name}")
    print("next: enable and start the keepass-auto-merge path unit and timer")
    return EXIT_OK


def verify_command(args: argparse.Namespace) -> int:
    credential_path = args.credential_file or credential.default_path()
    password = credential.read(credential_path)
    master = args.master
    if master is None:
        config = load(args.config)
        master = config.master_path
    unlock_check(master, password)
    print(f"credential unlocks {master}")
    return EXIT_OK


def check(config: Config) -> int:
    found = discover(config)
    print(f"master:  {found.master}")
    print(f"watch:   {config.watch_directory}")
    print(f"pattern: {config.conflict_glob}")
    print(f"on merged: {config.on_merged} -> {config.archive_path}")
    if not found.has_work:
        print("nothing to do: no conflict files found")
        return EXIT_OK

    print(f"\n{len(found.conflicts)} conflict file(s), oldest first:")
    for path in found.conflicts:
        stat = path.stat()
        print(f"  {path.name}  {stat.st_size} bytes  mtime {int(stat.st_mtime)}")
    return EXIT_OK


def entrypoint() -> None:
    raise SystemExit(main())
