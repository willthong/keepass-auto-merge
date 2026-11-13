# keepass-auto-merge

Folds KeePass *sync-conflict* copies (Nextcloud, Dropbox, Syncthing…) back into a single master
KDBX, non-destructively, on a systemd schedule.

The merge itself is [`keepassxc-cli merge`](https://keepassxc.org): the reference implementation,
keep-newer, history preserved, deletions never applied (see `docs/adr/0001`). This project is the
orchestration around it: discovery, credential handling, backups, atomic replacement, and a loud
report when a merge is not a clean fast-forward.

## How it behaves

- The **master database** and every file matching the conflict pattern live in one watch directory.
- Each conflict file, oldest first, is merged into a copy of the master; the copy is then renamed
  over the master, so an interrupted run leaves the previous master intact.
- The master is backed up to a hidden `.<name>.<timestamp>.bak` before each run, keeping the last
  `backup_keep` (default 10, `0` disables).
- Merged conflict files are moved to the archive directory (`.merged` by default) or deleted, as
  configured.
- Before each merge the two databases are compared. Anything that is not a clean fast-forward is
  logged at `ERROR` naming the affected entries, and the run exits `2`.
- The credential is the master password, stored with `systemd-creds` and handed to the service via
  `LoadCredential=`. It is never in the config file, argv, or the environment.

## Exit codes

| Code | Meaning |
|------|---------|
| `0`  | nothing to do, or every merge was a clean fast-forward |
| `1`  | a merge or configuration failed |
| `2`  | merged, but a human should read the journal |

## Install

Download the `.deb` from [Releases](https://github.com/willthong/keepass-auto-merge/releases):

```sh
sudo apt install ./keepass-auto-merge_<version>_all.deb
sudo keepass-auto-merge provision      # reads the master password on stdin
sudo systemctl start keepass-auto-merge.path keepass-auto-merge.timer
keepass-auto-merge verify
```

## Configure

`/etc/keepass-auto-merge/config.toml`:

```toml
watch_directory = "/srv/vaults"
master_filename = "keepass.kdbx"
conflict_glob   = "*sync-conflict*"
on_merged       = "archive"   # or "delete"
archive_dir     = ".merged"
backup_keep     = 10          # 0 disables backups
timer_interval  = "10min"
credential_name = "keepass-auto-merge.password"  # must match provision --name
```

## Develop

```sh
uv sync                                   # dependencies, including dev tools
uv run pytest                             # full suite (needs keepassxc-cli)
uv run ruff check . && uv run ruff format .
uv run pre-commit run --all-files          # what CI runs
```

Integration tests drive the real `keepassxc-cli` and are skipped when it is not installed.
