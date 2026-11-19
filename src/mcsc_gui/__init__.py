"""Public package interface for the Minecraft Server Creator."""

from ._pymcsc_check import ensure_pymcsc

# Must run before anything imports the pymcsc library (``mcsc``): see _pymcsc_check
ensure_pymcsc()

__all__ = ["main"]


def main() -> int:
    """Application entry point used by the package CLI (``mcsc``)."""
    # Imported lazily so that importing a subpackage (e.g. ``mcsc_gui.core``)
    # doesn't load Qt.
    from .qt_main import main as qt_main  # pylint: disable=import-outside-toplevel

    return qt_main()
