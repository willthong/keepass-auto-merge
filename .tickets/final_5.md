## What to build

The thing that makes this a service rather than a script: systemd units that run the merge both
when a conflict file appears and periodically as a safety net.

Three units. A oneshot service that runs `keepass-auto-merge run`, obtains the credential through
`LoadCredential=`, and runs as the dedicated `_keepass-merge` user. A path unit watching the watch
directory for changes. A timer that re-runs the service every ten minutes, so conflict files that
appeared while the service was down are still picked up.

The path unit should also fire on service start, and the service must be safe to run concurrently
with itself (a second invocation must not corrupt the master), so overlapping triggers cannot
interleave.

## Acceptance criteria

- [ ] Unit files are generated from the config (watch directory, credential name) rather than hardcoded
- [ ] The service runs as `_keepass-merge` with the credential available in `$CREDENTIALS_DIRECTORY`
- [ ] The timer fires every ten minutes
- [ ] The path unit watches the configured watch directory
- [ ] Two overlapping runs cannot corrupt the master: the second waits or exits cleanly
- [ ] Unit files pass `systemd-analyze verify`

## Blocked by

- #3
- #2
- #4
