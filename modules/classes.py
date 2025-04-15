"""
Classes
"""

import asyncio
import psutil

from modules.logger import RotatingLogger


logger = RotatingLogger()


class ProcessMonitor:
    """
    Monitor a process system resource usage
    """

    def __init__(self, process=None, interval: int = 1):
        self.process = process
        self.interval = interval
        self.active = False
        self.ram_usage = 0
        self.cpu_usage = 0
        self.disk_read = 0
        self.disk_write = 0
        logger.info(f"{self} initialized")

    def __repr__(self):
        if self.process:
            return f"ProcessMonitor(pid={self.process.pid}, active={self.active})"
        return f"ProcessMonitor(active={self.active})"

    def stop(self):
        """Stop monitoring the process"""
        self.active = False
        self.ram_usage = 0
        self.cpu_usage = 0
        self.disk_read = 0
        self.disk_write = 0
        logger.info(f"{self} stopped")

    async def run(self):
        """Start monitoring the process"""
        if not self.process:
            logger.warning("No process to monitor. Use the 'process' attribute to set one.")
            return

        if self.active:
            return

        try:
            proc = psutil.Process(self.process.pid)

            prev_disk_read = 0
            prev_disk_write = 0

            logger.info(f"{self} started")

            while self.process.returncode is None:
                self.active = True
                # Get all child processes
                children = proc.children(recursive=True)

                # RAM usage in MB (sum of parent and children)
                self.ram_usage = round(
                    (
                        proc.memory_info().rss
                        + sum(child.memory_info().rss for child in children)
                    )
                    / (1024 * 1024),
                    2,
                )

                # CPU usage as a percentage (sum of parent and children)
                self.cpu_usage = round(
                    proc.cpu_percent(interval=0.1)
                    + sum(child.cpu_percent(interval=0.1) for child in children),
                    2,
                )

                # Disk I/O (read and write in MB, current cycle)
                io_counters = proc.io_counters()
                current_disk_read = io_counters.read_bytes
                current_disk_write = io_counters.write_bytes
                for child in children:
                    child_io = child.io_counters()
                    current_disk_read += child_io.read_bytes
                    current_disk_write += child_io.write_bytes

                # Calculate current cycle usage
                self.disk_read = round(
                    (current_disk_read - prev_disk_read) / (1024 * 1024), 2
                )
                self.disk_write = round(
                    (current_disk_write - prev_disk_write) / (1024 * 1024), 2
                )

                # Update previous values
                prev_disk_read = current_disk_read
                prev_disk_write = current_disk_write

                await asyncio.sleep(self.interval)

        except psutil.NoSuchProcess:
            logger.info("The process has exited.")
            self.active = False

        except Exception as e:
            logger.error(f"Error monitoring process: {e}")
            self.active = False

        finally:
            if self.active:
                self.stop()
