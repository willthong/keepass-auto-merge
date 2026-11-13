## What to build

A tagged release publishes installable artefacts, so a user can install without cloning.

On a `v*` tag, a workflow builds the Python wheel and the `.deb` and attaches both to a GitHub
Release, with notes describing what changed. The `.deb` from the release must be installable on a
clean Ubuntu runner, and the installed CLI must report its version.

## Acceptance criteria

- [ ] Pushing a `v*` tag creates a GitHub Release with the wheel and the `.deb` attached
- [ ] The published `.deb` installs on a clean Ubuntu runner
- [ ] The installed `keepass-auto-merge --version` reports the released version
- [ ] Release notes are generated from commits since the previous tag

## Blocked by

- #6
- #7
