## What to build

The merge itself: fold every discovered conflict file into the master database, oldest-modified
first, in a way that cannot lose data and cannot leave a half-written master behind.

For each conflict file, in mtime order: back up the master once per run to a hidden
timestamped sibling file, copy the master to a temp file in the same directory, run
`keepassxc-cli merge` with the shared credential against the temp copy, atomically rename the temp
file over the master, and move the conflict file into the archive directory (or delete it, if
configured that way). Conflict files are opened read-only and never modified.

If any conflict file fails to merge, the master must be left exactly as it was, that conflict file
must remain in place, and already-merged conflict files stay merged. Backup retention is enforced
after a successful run.

A `--dry-run` flag performs discovery and reports what would happen without writing anything.

## Acceptance criteria

- [ ] Two conflict files merge into the master; every entry from both is present in the master
- [ ] Existing master entries that are not in any conflict file are still present after merging
- [ ] Entries modified in a conflict file win over the older master version, and history is preserved
- [ ] The master is backed up once per run to a hidden timestamped file, and old backups beyond the retention count are pruned
- [ ] Successfully merged conflict files end up in the archive directory (or are deleted when configured)
- [ ] A failing merge leaves the master byte-identical to before the run and leaves the conflict file in place
- [ ] The master is never observed half-written: it is replaced by atomic rename
- [ ] `--dry-run` writes nothing at all

## Blocked by

- #1
