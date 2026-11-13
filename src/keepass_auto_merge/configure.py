"""Applying configuration: validate, merge, write atomically (ADR-0004)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import config


def apply(path: Path, overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge `overrides` into the config at `path`, validate, and write it back.

    Values the operator is not overriding are preserved, keys this version does not know about are
    dropped (a repaired file is a features: `configure` must fix a hand-broken config).
    """
    existing = config.read_permissive(path)
    values = {**config.DEFAULT_VALUES, **existing}
    for key, value in overrides.items():
        if value is not None:
            values[key] = str(value) if key == "watch_directory" else value

    # Validate through the same path every other verb uses, so `configure` cannot write a file
    # that the service would then refuse to load.
    config.from_mapping(dict(values), source=path)
    config.write(path, values)
    return values
