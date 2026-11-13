"""Command line entry point.

Exit codes are part of the contract: 0 success, 1 failure, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, credential, units
from . import configure as configuration
from .config import SETTINGS, Config, ConfigError, NotConfigured, load
from .discovery import DiscoveryError, discover
from .engine import EngineError, unlock_check
from .merge import AlreadyRunning
from .merge import run as run_merge

DEFAULT_CONFIG = Path("/etc/keepass-auto-merge/config.toml")

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_ATTENTION = 2


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
    run_cmd.add_argument(
        "--credential-file",
        type=Path,
        default=None,
        help="read the credential from this file instead of systemd's $CREDENTIALS_DIRECTORY",
    )

    provision_cmd = sub.add_parser(
        "provision",
        parents=[common],
        help="encrypt the master password into the system credential store (reads stdin)",
    )
    provision_cmd.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="credential file to write (default: /etc/credstore.encrypted/<name>)",
    )
    provision_cmd.add_argument(
        "--name",
        default=None,
        help="credential name (default: credential_name from the config file)",
    )

    verify_cmd = sub.add_parser(
        "verify",
        parents=[common],
        help="prove the stored credential unlocks the master database",
    )
    verify_cmd.add_argument("--credential-file", type=Path, default=None)
    verify_cmd.add_argument("--master", type=Path, default=None)

    units_cmd = sub.add_parser(
        "units",
        parents=[common],
        help="write the systemd units for this config (site-specific watch paths)",
    )
    units_cmd.add_argument("--output-dir", type=Path, default=Path("/usr/lib/systemd/system"))

    configure_cmd = sub.add_parser(
        "configure",
        parents=[common],
        help="write the configuration file and regenerate the units",
    )
    for setting in SETTINGS:
        if setting.kind is int:
            configure_cmd.add_argument(
                setting.flag, type=int, default=None, help=setting.description
            )
        else:
            configure_cmd.add_argument(setting.flag, default=None, help=setting.description)
    configure_cmd.add_argument(
        "--units-dir",
        type=Path,
        default=Path("/etc/systemd/system"),
        help="where to write the regenerated units",
    )
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
        if args.command == "configure":
            return configure_command(args)
        if args.command == "verify":
            return verify_command(args)

        config = load(args.config)
        if args.command == "check":
            return check(config)
        if args.command == "run":
            return run_command(args, config)
        if args.command == "units":
            return units_command(args, config)
    except NotConfigured as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    except (ConfigError, DiscoveryError, credential.CredentialError, EngineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    print(f"error: unknown command {args.command}", file=sys.stderr)
    return EXIT_USAGE


def provision_command(args: argparse.Namespace) -> int:
    # The config decides the credential name so it cannot drift from LoadCredential= in the unit.
    name = args.name or _configured_credential_name(args.config)
    dest = args.dest or credential.provision_path(name)
    password = credential.prompt_password()
    credential.provision(password, dest, name=name)
    print(f"credential written to {dest}")
    print(f"name: {name}")
    print("next: enable and start the keepass-auto-merge path unit and timer")
    return EXIT_OK


def run_command(args: argparse.Namespace, config: Config) -> int:
    password = credential.load(args.credential_file, config.credential_name)
    try:
        report = run_merge(config, password, dry_run=args.dry_run)
    except AlreadyRunning as exc:
        print(f"skipping: {exc}")
        return EXIT_OK

    if args.dry_run:
        if not report.planned:
            print("dry run: nothing to do")
            return EXIT_OK
        print(f"dry run: would merge {len(report.planned)} conflict file(s)")
        for path in report.planned:
            print(f"  {path.name}")
        return EXIT_OK

    print(f"merged {len(report.merged)} conflict file(s) into {config.master_path}")
    if report.backup:
        print(f"backup: {report.backup}")
    for path in report.archived:
        print(f"archived: {path}")
    for path in report.deleted:
        print(f"deleted: {path}")
    for path, reason in report.failed:
        print(f"error: {path.name}: {reason}", file=sys.stderr)
    if not report.ok:
        return EXIT_FAILURE
    for line in report.attention:
        print(line, file=sys.stderr)
    return EXIT_ATTENTION if report.needs_attention else EXIT_OK


def configure_command(args: argparse.Namespace) -> int:
    flags = {setting.name: getattr(args, setting.name.replace("-", "_")) for setting in SETTINGS}
    given = {name: value for name, value in flags.items() if value is not None}

    if not given:
        if not _interactive():
            print(
                "error: no terminal to prompt on; pass the settings as flags",
                file=sys.stderr,
            )
            for setting in SETTINGS:
                print(f"  {setting.flag}  {setting.description}", file=sys.stderr)
            return EXIT_USAGE
        given = _interactive_answers(args.config)
        if given is None:
            return EXIT_FAILURE

    values = configuration.apply(args.config, given)
    print(f"wrote {args.config}")
    for setting in SETTINGS:
        print(f"  {setting.name} = {values.get(setting.name)}")
    return _regenerate_units(args, values)


def _regenerate_units(args: argparse.Namespace, values: dict) -> int:
    try:
        args.units_dir.mkdir(parents=True, exist_ok=True)
        for name, content in units.render(load(args.config)).items():
            (args.units_dir / name).write_text(content, encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot write units to {args.units_dir}: {exc.strerror}", file=sys.stderr)
        print(
            "the configuration was written; re-run as root, or pass --units-dir",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    print(f"wrote units to {args.units_dir}")

    if _systemd_available():
        for command in (
            ["systemctl", "daemon-reload"],
            ["systemctl", "enable", "--now", "keepass-auto-merge.path"],
            ["systemctl", "enable", "--now", "keepass-auto-merge.timer"],
        ):
            subprocess.run(command, check=False)
        print("reloaded systemd and enabled the path unit and timer")
        return EXIT_OK

    print("systemd is not running here; apply the units with:")
    print("  systemctl daemon-reload")
    print("  systemctl enable --now keepass-auto-merge.path keepass-auto-merge.timer")
    return EXIT_OK


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _interactive_answers(config_path: Path) -> dict | None:
    """Ask the one setting nothing can invent, explain every other, then confirm once."""
    current = _current_values(config_path)
    print("Configure keepass-auto-merge. Enter accepts the value in brackets.")
    answers: dict = {}

    required = SETTINGS[0]
    print(f"\n{required.name}: {required.description}")
    answer = input(f"  {required.flag} [{current.get(required.name) or ''}]: ").strip()
    if answer:
        answers[required.name] = answer

    print("\nEvery other setting (defaults shown; pass the flag to change one):")
    for setting in SETTINGS[1:]:
        value = current.get(setting.name)
        print(f"  {setting.flag} [{value}]")
        print(f"      {setting.description}")
    answers = {**current, **answers}
    answers.pop("watch_directory", None) if not answers.get("watch_directory") else None

    print("\nResulting configuration:")
    for setting in SETTINGS:
        print(f"  {setting.name} = {answers.get(setting.name)}")
    if input("Write this configuration? [Y/n]: ").strip().lower() in {"n", "no"}:
        print("aborted: nothing written")
        return None
    return answers


def _current_values(config_path: Path) -> dict:
    try:
        loaded = load(config_path)
    except ConfigError:
        from .config import DEFAULTS

        return dict(DEFAULTS)
    return {setting.name: getattr(loaded, setting.name) for setting in SETTINGS}


def _systemd_available() -> bool:
    return os.geteuid() == 0 and Path("/run/systemd/system").is_dir() and shutil.which("systemctl")


def _configured_credential_name(config_path: Path) -> str:
    """The credential name from the config, falling back to the default when absent."""
    try:
        return load(config_path).credential_name
    except ConfigError:
        return credential.DEFAULT_NAME


def units_command(args: argparse.Namespace, config: Config) -> int:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in units.render(config).items():
        target = args.output_dir / name
        target.write_text(content, encoding="utf-8")
        print(f"wrote {target}")
    print("run: sudo systemctl daemon-reload")
    print("run: sudo systemctl enable --now keepass-auto-merge.path keepass-auto-merge.timer")
    return EXIT_OK


def verify_command(args: argparse.Namespace) -> int:
    password = credential.load(args.credential_file, _configured_credential_name(args.config))
    master = args.master
    if master is None:
        config = load(args.config)
        master = config.master_path
    unlock_check(master, password)
    print(f"credential unlocks {master}")
    return EXIT_OK


def check(config: Config) -> int:
    print(f"config: {config.source}")
    for setting in SETTINGS:
        print(f"{setting.name}: {getattr(config, setting.name)}")
    found = discover(config)
    print(f"master:  {found.master}")
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
