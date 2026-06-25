"""xu-wiki: relation-driven three-layer wiki engine for AI agents.

Version is resolved dynamically so the value follows the wheel built by
maturin / cargo, instead of drifting in a hand-edited string.

Resolution order:
1. `xu._core.__pkg_version__` (set by build.rs / pyproject.toml when
   maturin compiles the Rust extension against the current Cargo.toml).
2. `importlib.metadata.version("xu-wiki")` (the wheel's METADATA).
3. Fallback: a hard-coded fallback string for editable installs where
   neither of the above is available.
"""
from __future__ import annotations

__version__ = "0.2.1+unknown"


def _resolve_version() -> str:
    # 1. The Rust extension exposes the cargo version when built.
    try:
        from xu._core import __pkg_version__  # type: ignore
        v = str(__pkg_version__).strip()
        if v:
            return v
    except Exception:
        pass

    # 2. Wheel / installed-package metadata.
    try:
        from importlib.metadata import version as _v
        return _v("xu-wiki")
    except Exception:
        pass

    return __version__


__version__ = _resolve_version()
