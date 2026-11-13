# Regenerate the config file from `configure`, and drop comments in it

A `configure` verb now writes the configuration file directly: it loads the existing file
permissively, merges any flags (or the answers to its interactive prompts), validates, and writes
the whole file back with `tomli-w`, every key present at its effective value and **no comments**.
Comments in the conffile are deprecated: the README documents every key, and the interactive
prompts describe each value as they ask for it.

We rejected two alternatives. A hand-rolled line editor would have preserved comments without a
dependency, but maintaining a TOML writer by hand in a security tool is worse than a declared
dependency. A drop-in `config.local.toml` would have preserved the packaged file untouched, but
added a precedence rule between two files that nobody would remember. `tomli-w` cannot emit
comments at all, which is what forced the documentation move rather than a choice to write a
comment-free file by hand.

Consequences worth knowing:

- Rewriting is atomic (tempfile + rename) with no backup, and an existing conffile's comments are
  discarded silently. Divergence between the packaged and local conffile can therefore surface as
  a `dpkg` prompt on upgrade, which is now the normal, expected behaviour for an edited conffile.
- `configure` parses permissively, so a hand-broken file (unknown keys) is repaired instead of
  blocking the verb whose job is repair. Unknown keys are dropped.
- `tomli-w` (the `python3-tomli-w` distribution package on Debian and Ubuntu) becomes the only
  third-party runtime dependency.
- The packaged conffile ships `0644` and carries defaults but no `watch_directory`, so a fresh
  install is explicitly *unconfigured* rather than pointing at a directory that does not exist.
