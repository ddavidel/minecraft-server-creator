"""
Update module for MCSC
"""

import logging
import subprocess
import sys
from importlib.metadata import version

import requests

from mcsc_gui.config.settings import PACKAGE_NAME, PYPI_PACKAGE_URL

logger = logging.getLogger(__name__)


def get_current_version() -> str:
    """
    Get current version
    """
    try:
        current = version(PACKAGE_NAME)
    except Exception:  # pylint: disable=broad-exception-caught
        current = "0.0.0"

    logger.info(f"Currently running verion {current}")
    return current


def check_for_updates() -> bool:
    """
    Check for updates
    """
    logger.info("Checking for updates...")
    current_version = get_current_version()

    response = requests.get(PYPI_PACKAGE_URL, timeout=5)
    if response.status_code == 200:
        latest_version: str = response.json()["info"]["version"]
    else:
        logger.warning("Unable to check for updates")
        return False

    try:
        current_version = int(current_version.replace(".", ""))
        latest_version = int(latest_version.replace(".", ""))
    except ValueError:
        return False

    return latest_version > current_version


# New update workflow
def update_mcsc() -> bool:
    """Update the package via pip and restart the program."""
    try:
        # Run update
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE_NAME]
        )

        logger.info(f"{PACKAGE_NAME} updated successfully!")
        return True

    except subprocess.CalledProcessError:
        logger.error(
            f"Error: update failed. Try running 'pip install {PACKAGE_NAME} --upgrate' manually."
        )
        return False
