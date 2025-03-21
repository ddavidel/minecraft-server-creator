"""
Update module for MCSC
"""
import sys
import subprocess
import os
import importlib
import shutil
from datetime import datetime
import requests

from config.settings import (
    UPDATE_BRANCH,
    GITHUB_REPO,
    VERSION_FILENAME,
    GITHUB_FILE_URL,
    BACKUP_DIR,
)

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
        with open(VERSION_FILENAME, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        return "0.0.0"


def check_for_updates() -> bool:
    """
    Check for updates
    """
    current_version = get_current_version()

    try:
        response = requests.get(GITHUB_FILE_URL, timeout=5)
        latest_version = response.text.strip()
    except requests.exceptions.RequestException:
        return False

    try:
        current_version = int(current_version.replace(".", ""))
        latest_version = int(latest_version.replace(".", ""))
    except ValueError:
        return False

    return latest_version > current_version


class Update:
    """
    Update class
    """

    def __init__(self):
        self.update_available = check_for_updates()
        self.app_dir = get_app_dir()
        self.backup_dir = os.path.join(self.app_dir, BACKUP_DIR)
        self.status = ""
        self.completed = False

    async def run(self):
        """
        Run the update
        """
        if self.update_available:
            # Update status
            self.status = "Starting update"
            # Backup the app
            # self.create_backup()

            # Update update_files.py
            self.replace_file(filename="update_files.py", path="config")
            update_files = importlib.import_module("config.update_files").UPDATE_FILES

            # Update the app
            for file in update_files:
                self.replace_file(
                    filename=file["filename"].strip(), path=file["path"].strip()
                )

            # Post update routines
            self.post_update_routines()

            self.status = "Update complete"
            self.completed = True

        else:
            print("No updates available")

    def download_file(self, filename: str, path: str):
        """
        Download file
        """
        url = f"{BASE_URL}/{path}/{filename}"
        response = requests.get(url, timeout=5)
        return response.content

    def replace_file(self, filename: str, path: str):
        """
        Replace file
        """
        self.status = f"Updating {filename}"

        # Download file
        content = self.download_file(filename=filename, path=path)

        os.makedirs(os.path.join(self.app_dir, *path.split("/")), exist_ok=True)

        # Overwrite file
        with open(os.path.join(self.app_dir, *path.split("/"), filename), "wb") as file:
            file.write(content)
            file.flush()

        self.status = f"Updated {filename}"
        print(f"Updated {filename}")

    def create_backup(self):
        """
        Create a backup of entire app
        """
        self.status = "Creating backup"

        # Create backup
        os.makedirs(self.backup_dir, exist_ok=True)

        # Create zip
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = os.path.join(self.backup_dir, f"project_backup_{timestamp}.zip")
        shutil.make_archive(zip_name.replace(".zip", ""), "zip", self.app_dir)

        self.status = "App backed up"
        print(f"App backed up to: {zip_name}")

    def post_update_routines(self):
        """Execute post update routines"""
        self.status = "Running post-update routines"
        print("\nRunning post-update routines\n")

        # Run routines
        self._routine_install_requirements()

        self.status = "\nPost-update routines completed\n"
        print("\nPost-update routines completed\n")

    def _routine_install_requirements(self):
        """Installs requirements from requirements.txt file"""
        self.status = "Updating requirements"
        print("Updating requirements")
        subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            "requirements.txt",
            "--no-warn-script-location",
        ],
        check=True,
    )
