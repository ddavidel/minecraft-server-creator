"""Module entry point for the project CLI (``mcsc`` / ``python -m mcsc_gui``)."""

import sys


def main() -> None:
    """Run the Qt desktop app."""
    from .qt_main import main as qt_main  # pylint: disable=import-outside-toplevel

    sys.exit(qt_main())


if __name__ == "__main__":
    main()
