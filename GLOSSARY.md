# KeePass Auto-Merge

A service that watches a directory for KeePass databases that have diverged (for example
Nextcloud/Dropbox "sync-conflict" copies) and folds them back into a single master database
without destroying data.

## Language

**Master database**:
The single authoritative KDBX file that accumulates the contents of every conflict file.
_Avoid_: primary database, target, main DB

**Conflict file**:
A KDBX file matched by the configured source pattern (for example `*sync-conflict*`) whose
entries are merged into the master database.
_Avoid_: source database, stray, orphan

**Archive directory**:
A subdirectory of the watch directory where successfully merged conflict files are moved so they
are not re-merged on the next run.
_Avoid_: processed, done, merged-dir

**Clean fast-forward**:
A conflict file whose state is strictly ahead of the master: no entry is missing from it that
exists in the master, and no shared entry is newer in the master. The only merges that need no
human attention.
_Avoid_: no-conflict merge, trivial merge

**Non-destructive merge**:
Folding a conflict file into the master database without ever removing entries already present
in the master.
_Avoid_: sync, synchronize, reconcile

**Credential**:
The master password shared by the master database and every conflict file, stored with
systemd-creds and supplied to the merge process.
_Avoid_: secret, password, passphrase

**Watch directory**:
The configured directory that holds the master database and the conflict files the service scans.
_Avoid_: sync folder, Dropbox folder, data dir
