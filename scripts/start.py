"""Project-local launcher for debugging and local app startup."""

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
    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        os.environ["MCSC_DEBUG"] = "1"

    import mcsc_gui

    app = getattr(mcsc_gui, "ServerCreatorGUI", None)
    if app is None:
        raise RuntimeError("The package does not expose a ServerCreatorGUI entry point.")

    app().run(debug=os.environ.get("MCSC_DEBUG", "").lower() in {"1", "true", "yes"})


if __name__ == "__main__":
    main()