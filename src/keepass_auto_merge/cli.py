"""Command line entry point.

Exit codes are part of the contract: 0 success, 1 failure, 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import Config, ConfigError, load
from .discovery import DiscoveryError, discover

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
        config = load(args.config)
        if args.command == "check":
            return check(config)
    except (ConfigError, DiscoveryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    print(f"error: unknown command {args.command}", file=sys.stderr)
    return EXIT_USAGE


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
