# Use keepassxc-cli as the merge engine

We shell out to KeePassXC's `keepassxc-cli merge` to fold each conflict file into the master
database, and keep our own code (a small `ty` CLI in Python) responsible for discovery,
configuration, secret handling, and reporting.

We considered `pykeepass`, the actively-maintained native Python library (v4.2.0, KDBX3/KDBX4),
but rejected it: it has no merge API, so we would have to re-implement KeePass's conflict
resolution and history-merging ourselves for a security-sensitive tool, and it is GPL-3.0, which
would force our package to be GPL too. `keepassxc-cli` is the reference implementation, merges
non-destructively by default (keep-newer, history preserved, deletions not applied), and supports
`--dry-run`. The cost is a runtime dependency on KeePassXC.
