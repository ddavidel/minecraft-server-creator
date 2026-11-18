"""
Repair the pymcsc library after an upgrade from MCSC 2.x.

MCSC 2.x installed the app itself as the ``mcsc`` package, the same name pymcsc
uses. When pip upgrades from 2.x it installs pymcsc first and then uninstalls
the old app, deleting ``mcsc/__init__.py``, which by then belongs to pymcsc.
``mcsc`` is then left as a broken namespace package. This module detects that
and reinstalls pymcsc before anything imports it.

Runs before logging is configured, so it reports on stderr.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import subprocess
import sys

REPAIR_HINT = "pip install --force-reinstall --no-deps pymcsc"


def pymcsc_available() -> bool:
    """True if ``mcsc`` is the working pymcsc library."""
    try:
        from mcsc import ServerManager  # pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        return False
    return True


def _forget_mcsc_modules() -> None:
    """Drop the half-imported ``mcsc`` modules, so the next import reads the repaired files."""
    for name in [n for n in sys.modules if n == "mcsc" or n.startswith("mcsc.")]:
        del sys.modules[name]
    importlib.invalidate_caches()


def _requirement() -> str:
    """The installed pymcsc version (still listed by pip even when its files are broken)."""
    try:
        return f"pymcsc=={importlib.metadata.version('pymcsc')}"
    except importlib.metadata.PackageNotFoundError:
        return "pymcsc"


def ensure_pymcsc() -> None:
    """Make sure pymcsc can be imported, reinstalling it once if it's broken."""
    if pymcsc_available():
        return

    requirement = _requirement()
    print(f"MCSC: the pymcsc library is damaged, reinstalling {requirement}...", file=sys.stderr)
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", requirement]
        )
    except (OSError, subprocess.CalledProcessError) as e:
        raise RuntimeError(
            f"Can't repair the pymcsc library ({e}). Run '{REPAIR_HINT}' and restart MCSC."
        ) from e

    _forget_mcsc_modules()
    if not pymcsc_available():
        raise RuntimeError(f"The pymcsc library is still broken. Run '{REPAIR_HINT}' and restart MCSC.")
    print("MCSC: pymcsc repaired.", file=sys.stderr)
