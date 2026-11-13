## What to build

Developer guardrails so that the test suite and linters run the same way on a laptop and in CI.

Python `pre-commit` hooks for formatting, import sorting, and linting, plus basic hygiene hooks
(whitespace, end-of-file, YAML/TOML validity, large files). Hooks must be installable with one
documented command and must run over the whole tree.

A GitHub Actions workflow that runs on every push and pull request: install dependencies with `uv`,
run the pre-commit hooks, and run the pytest suite. The workflow must fail the build on the first
failing hook or test.

## Acceptance criteria

- [ ] `pre-commit run --all-files` passes on a clean checkout
- [ ] Deliberately misformatted Python makes the hooks fail
- [ ] CI runs pytest and the hooks on push and pull request
- [ ] CI fails when a test fails
- [ ] `README` documents the local commands for tests, lint, and hooks

## Blocked by

- #1
