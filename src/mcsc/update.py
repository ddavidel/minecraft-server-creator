"""
Update module for MCSC
"""

import sys
import subprocess
import os
import importlib
import shutil
from datetime import datetime
from importlib.metadata import version
import requests

from mcsc.config.settings import (
    UPDATE_BRANCH,
    GITHUB_REPO,
    GITHUB_FILE_URL,
    BACKUP_DIR,
    PACKAGE_NAME,
)
from mcsc.modules.logger import RotatingLogger

logger = RotatingLogger()

BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/refs/heads/{UPDATE_BRANCH}"


def get_app_dir() -> str:
    """
    Get the app directory
    """
    return os.path.dirname(os.path.realpath(__file__))


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

    response = requests.get(f"https://pypi.org/pypi/{PACKAGE_NAME}/json", timeout=5)
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
