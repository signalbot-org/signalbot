from __future__ import annotations

import importlib.metadata


def package_version(name: str) -> str:
    """The installed version of package `name`, or `"0.0.0"` if it isn't
    installed (e.g. running from a source checkout)."""
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"
