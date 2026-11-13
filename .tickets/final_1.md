## What to build

A working `keepass-auto-merge` command that can tell you what it *would* do, without touching any
database. It reads a TOML config, locates the master database and every conflict file in the watch
directory, and prints the plan.

Config keys: watch directory, master filename, conflict-file glob (default `*sync-conflict*`),
merge mode, conflict-file handling (`archive` or `delete`), archive directory name, backup
retention count, timer interval. A single TOML file, path overridable with `--config`.

Discovery must find the configured master filename in the watch directory and every file matching
the conflict glob, case-insensitively, while excluding the archive directory.

`keepass-auto-merge check` prints the plan: which master file it found, which conflict files it
found (with sizes and mtimes), and the configured behaviour. Nothing is read with the credential,
nothing is written.

## Acceptance criteria

- [ ] `check` on a directory with one master and two conflict files lists all three
- [ ] Conflict matching is case-insensitive and honours a custom glob
- [ ] Files inside the archive directory are never listed as conflict files
- [ ] A missing or unreadable master database is reported as an error, non-zero exit
- [ ] A missing config file is reported as an error, non-zero exit
- [ ] Config is TOML, has documented defaults for every key, and never contains the credential

## Blocked by

None (can start immediately).
