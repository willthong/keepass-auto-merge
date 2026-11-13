## What to build

`keepassxc-cli merge` is always non-destructive: it keeps the newer version of an entry and never
applies deletions. That is safe, but it hides intent — if a conflict file deliberately deleted an
entry, or the master holds a newer version of an entry the conflict file also changed, the operator
should be told loudly rather than silently getting a keep-newer result.

Before merging each conflict file, compare it against the master entry-by-entry by UUID and
modification time. A **clean fast-forward** is: no entry present in the master is missing from the
conflict file (no deletions requested), and no entry is newer in the master (no divergence). Only a
clean fast-forward proceeds quietly.

Anything else is logged at ERROR level, naming each affected entry by UUID and title, with the
reason (deleted in conflict file / newer in master / changed on both sides). The run still completes
non-destructively, and the exit code is `2` to signal that a human should look at the journal.

Exit codes: `0` nothing to do or all clean fast-forwards, `1` failure, `2` merged but attention
needed.

## Acceptance criteria

- [ ] A conflict file that only adds entries is classified as a clean fast-forward and the run exits `0`
- [ ] A conflict file missing an entry the master has is logged at ERROR naming that entry, exit code `2`
- [ ] An entry modified in the master after the conflict file's copy is logged at ERROR naming that entry
- [ ] Entries changed on both sides are reported as such
- [ ] The merged master is identical whether or not the classification ran (classification is read-only)
- [ ] The documented exit codes are covered by tests

## Blocked by

- #2
