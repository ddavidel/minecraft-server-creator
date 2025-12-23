"""
Simple logger because i dont want to use logger module
"""

import os
import datetime
import glob
from mcsc.config import settings as mcssettings


class RotatingLogger:
    """
    Simple logger that rotates logs daily and deletes old logs.
    """

    LOG_RETENTION_DAYS = 0

    def __init__(self, log_dir=mcssettings.LOG_DIR_PATH):
        os.makedirs(log_dir, exist_ok=True)
        self.log_dir = log_dir

        # Generate or get log file path
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self.log_path = os.path.join(log_dir, f"logs_{today}.log")

        if self.LOG_RETENTION_DAYS > 0:
            # Clean up old logs
            self.cleanup_old_logs()

    def log(self, level, message):
        """Log a message with the specified level of severity"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {level.upper()} {message}"
        if mcssettings.DEBUG:
            print(log_message)

        with open(self.log_path, "a", encoding="utf-8") as log_file:
            log_file.write(log_message + "\n")

    def cleanup_old_logs(self):
        """Deletes log files older than LOG_RETENTION_DAYS."""
        cutoff_date = datetime.datetime.now() - datetime.timedelta(
            days=self.LOG_RETENTION_DAYS
        )

        # Find all log files matching the pattern
        log_files = glob.glob(os.path.join(self.log_dir, "mcsc_*.log"))

        for log_file in log_files:
            # Extract the date from the filename
            try:
                filename = os.path.basename(log_file)
                file_date_str = filename.replace("mcsc_", "").replace(".log", "")
                file_date = datetime.datetime.strptime(file_date_str, "%Y-%m-%d")

                # Delete files older than the retention period
                if file_date < cutoff_date:
                    os.remove(log_file)
                    print(f"Deleted old log file: {log_file}")

            except ValueError:
                pass  # Ignore files that don't match the date format

    def info(self, message: str):
        """
        Log an informational message.

        Args:
            message (str): The message to log.
        """
        self.log("INFO", message)

    def debug(self, message: str):
        """
        Log a debug message.

        Args:
            message (str): The message to log.
        """
        self.log("DEBUG", message)

    def warning(self, message: str):
        """
        Log a warning message.

        Args:
            message (str): The message to log.
        """
        self.log("WARNING", message)

    def error(self, message: str):
        """
        Log an error message.

        Args:
            message (str): The message to log.
        """
        self.log("ERROR", message)

    def critical(self, message: str):
        """
        Log a critical message.

        Args:
            message (str): The message to log.
        """
        self.log("CRITICAL", message)
