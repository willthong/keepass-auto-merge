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
sudo keepass-auto-merge configure --watch-directory /srv/vaults   # writes config + units
sudo keepass-auto-merge provision                                 # master password on stdin
keepass-auto-merge verify
keepass-auto-merge check
```

Use `apt install ./<file>.deb`, not `dpkg -i`: the package depends on `keepassxc` and
`python3-tomli-w`, and only apt resolves those. If you already ran `dpkg -i` and it stopped on
dependencies, finish the job with `sudo apt install -f`.

Upgrading from 0.1.0 replaces the packaged config file with the defaults-only version; if you
edited `/etc/keepass-auto-merge/config.toml` by hand, dpkg will ask before replacing it.

`configure` is the only supported way to write the configuration. Run it bare on a terminal to be
asked the questions, or pass flags for scripts and cron; it never prompts when there is no
terminal.

## Configuration

The file lives at `/etc/keepass-auto-merge/config.toml` and is **owned by `configure`**: do not
hand-edit it. `configure` rewrites the whole file atomically, in this order, with every key at its
effective value.

| Key | Flag | Default | Meaning |
|-----|------|---------|---------|
| `watch_directory` | `--watch-directory` | *(required)* | Directory holding the master database and the conflict files. Must already exist. |
| `master_filename` | `--master-filename` | `keepass.kdbx` | The authoritative database that every conflict file is merged into. |
| `conflict_glob` | `--conflict-glob` | `*sync-conflict*` | Case-insensitive glob for the files to merge. |
| `merge_mode` | `--merge-mode` | `keep-newer` | Only `keep-newer` is supported: deletions are never applied. |
| `on_merged` | `--on-merged` | `archive` | What happens to a conflict file after merging: `archive` or `delete`. |
| `archive_dir` | `--archive-dir` | `.merged` | Subdirectory of the watch directory where merged conflict files are kept. |
| `backup_keep` | `--backup-keep` | `10` | How many hidden timestamped master backups to keep. `0` disables backups. |
| `timer_interval` | `--timer-interval` | `10min` | How often the timer re-scans, on top of the path unit's watch. |
| `keepassxc_cli` | `--keepassxc-cli` | `keepassxc-cli` | Path to the merge engine. |
| `credential_name` | `--credential-name` | `keepass-auto-merge.password` | Name of the credential in the system credential store. Must match what `provision` wrote. |

**Comments in the config file are not preserved.** `configure` regenerates the file from the
values, so annotations are discarded; the table above and the interactive prompts are the
documentation. A key that `configure` does not recognise is dropped when the file is rewritten,
which is how a hand-broken config gets repaired.

The packaged file ships with every default and no `watch_directory`, so a fresh install is
explicitly unconfigured and every command says so instead of pointing at a directory that may not
exist. `keepass-auto-merge check` prints the effective configuration and the file it came from.

## Develop

```sh
uv sync                                   # dependencies, including dev tools
uv run pytest                             # full suite (needs keepassxc-cli)
uv run ruff check . && uv run ruff format .
uv run pre-commit run --all-files          # what CI runs
```

Integration tests drive the real `keepassxc-cli` and are skipped when it is not installed.
