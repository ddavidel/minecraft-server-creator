"""
Logging setup.

The app and the pymcsc library (``mcsc`` logger) log through the standard
``logging`` module; this module routes both to a daily log file.
"""

import datetime
import logging
import os

from mcsc_gui.config import settings as mcssettings

LOGGER_NAMES = ("mcsc", "mcsc_gui")
LOG_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(debug: bool = mcssettings.DEBUG, log_dir: str = mcssettings.LOG_DIR_PATH) -> None:
    """Send app and library logs to ``log_dir/logs_<date>.log`` (and the console in debug)."""
    global _configured  # pylint: disable=global-statement
    if _configured:
        return

    os.makedirs(log_dir, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    handlers: list[logging.Handler] = [
        logging.FileHandler(os.path.join(log_dir, f"logs_{today}.log"), encoding="utf-8")
    ]
    if debug:
        handlers.append(logging.StreamHandler())

    for handler in handlers:
        handler.setFormatter(formatter)

    for name in LOGGER_NAMES:
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG if debug else logging.INFO)
        for handler in handlers:
            logger.addHandler(handler)

    _configured = True
