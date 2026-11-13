## What to build

The one-time human step: storing the master password where the service can read it, and proving it
works.

`keepass-auto-merge provision` reads the master password from stdin (never an argument, never an
environment variable), encrypts it with `systemd-creds encrypt` into the system credential store,
and reports where it wrote it and with what name. It must refuse to continue if the password is
empty.

`keepass-auto-merge verify` reads the credential back and proves it unlocks the master database by
running a harmless `keepassxc-cli` inspection against it. Exit `0` when the credential unlocks the
master, non-zero with a clear message when it does not.

When running under systemd, the credential is read from `$CREDENTIALS_DIRECTORY`. Outside systemd,
an explicit credential file path may be given, so a human can run `verify` during setup.

## Acceptance criteria

- [ ] `provision` never echoes the password, accepts it only on stdin, and rejects empty input
- [ ] `provision` writes an encrypted credential that `systemd-creds decrypt` round-trips
- [ ] `verify` exits `0` when the credential unlocks the master database
- [ ] `verify` exits non-zero with a clear message for a wrong password
- [ ] Both commands work headless: no TTY, stdin not a terminal
- [ ] The credential name and path are documented as an ADR-0002 implementation detail

## Blocked by

None (can start immediately).
