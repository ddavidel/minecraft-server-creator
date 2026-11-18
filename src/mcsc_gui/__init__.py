"""Public package interface for the Minecraft Server Creator."""

from ._pymcsc_check import ensure_pymcsc

# Must run before anything imports the pymcsc library (``mcsc``): see _pymcsc_check
ensure_pymcsc()

from .main import ServerCreatorGUI  # noqa: E402  pylint: disable=wrong-import-position

__all__ = ["ServerCreatorGUI"]


def main() -> None:
    """Application entry point used by the package CLI."""
    ServerCreatorGUI().run()
