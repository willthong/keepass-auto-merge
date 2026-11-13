"""systemd units, generated from the config (ADR-0003).

A oneshot service plus a path unit for immediacy and a timer as the safety net for conflict files
that appeared while the service was down.
"""

from __future__ import annotations

from .config import Config

SERVICE = "keepass-auto-merge.service"
PATH_UNIT = "keepass-auto-merge.path"
TIMER = "keepass-auto-merge.timer"

CONFIG_PATH = "/etc/keepass-auto-merge/config.toml"


def render(config: Config, *, executable: str = "/usr/bin/keepass-auto-merge") -> dict[str, str]:
    """The three unit files as name -> content."""
    return {
        SERVICE: _service(config, executable),
        PATH_UNIT: _path_unit(config),
        TIMER: _timer(config),
    }


def _service(config: Config, executable: str) -> str:
    return f"""\
[Unit]
Description=Merge KeePass sync-conflict databases into the master database
Documentation=https://github.com/willthong/keepass-auto-merge
After=local-fs.target

[Service]
Type=oneshot
User=_keepass-merge
Group=_keepass-merge
LoadCredentialEncrypted={config.credential_name}
ExecStart={executable} run --config {CONFIG_PATH}
TimeoutStartSec=15min
Nice=10
# Root-owned directories only: the watch directory must be granted explicitly.
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
ReadWritePaths={config.watch_directory}
"""


def _path_unit(config: Config) -> str:
    return f"""\
[Unit]
Description=Watch for KeePass sync-conflict files

[Path]
PathExistsGlob={config.watch_directory}/{config.conflict_glob}
Unit={SERVICE}

[Install]
WantedBy=multi-user.target
"""


def _timer(config: Config) -> str:
    return f"""\
[Unit]
Description=Periodically re-scan for KeePass sync-conflict files

[Timer]
OnBootSec=5min
OnUnitActiveSec={config.timer_interval}
Unit={SERVICE}

[Install]
WantedBy=timers.target
"""
