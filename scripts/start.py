"""Project-local launcher for debugging and local app startup.

    python scripts/start.py          # start the app from the source tree
    python scripts/start.py --debug  # with DEBUG logs on the console
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> None:
    """Start the app using the repository source tree."""
    if "--debug" in sys.argv[1:]:
        os.environ["MCSC_DEBUG"] = "1"

    from mcsc_gui.qt_main import main as qt_main  # pylint: disable=import-outside-toplevel

    sys.exit(qt_main(sys.argv))


if __name__ == "__main__":
    main()
