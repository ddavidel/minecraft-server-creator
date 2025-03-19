"""
Forge server module
"""

import asyncio
import subprocess
import json
import os
import shutil
from uuid import uuid4
import numpy as np
import requests
from nicegui import binding, ui

from config import settings as mcssettings
from modules.translations import translate as _
from modules.classes import ProcessMonitor

from modules.servers.models import MinecraftServer


class ForgeServer(MinecraftServer):
    """
    Forge server class
    """
    @property
    def jar_path(self) -> str:
        """server's jar path"""
        return os.path.join(
            self.server_path,
            f"minecraft_server.{self.version.split('-')[0]}.jar",
        )

    @property
    def server_path(self) -> str:
        """server's jar path"""
        return os.path.join(self.settings["folder_path"], "server")

    def _init_forge_server(self):
        """Initializes forge server"""
        # install server
        assert self.jar_type == 2
        try:
            cmd = [
                "java",
                "-jar",
                "server.jar",
                "--installServer",
                "server",
            ]

            # Start the subprocess
            subprocess.run(
                cmd,
                cwd=self.settings["folder_path"],
                check=False,
            )

        except Exception as e:
            print(f"Error while initializing forge server {self.uuid}: {e}")

    def _set_user_jvm_args(self):
        """Sets set_user_jvm_args for FORGE server. ONLY FORGE SERVERS"""
        if self.jar_type == 2:
            user_jvm_args_path = os.path.join(self.server_path, "user_jvm_args.txt")
            args = f"-Xmx{self.settings['dedicated_ram']}G -Xms{self.settings['dedicated_ram']}G"

            # Wait for server folder to be created
            exists = bool(os.path.exists(self.server_path))
            while not exists:
                exists = bool(os.path.exists(self.server_path))

            if os.path.exists(user_jvm_args_path):
                with open(user_jvm_args_path, "w", encoding="utf-8") as file:
                    file.write(args)
                    file.flush()

            else:
                raise ValueError(_("Unsupported Forge Version. THIS IS NOT A BUG!"))

        else:
            raise ValueError("This is not a Forge server")

    async def start(self):
        """Starts the forge server"""
        self.starting = True
        try:
            if not os.path.exists(os.path.join(self.server_path, "run.bat")):
                raise ValueError(_("Unsupported Forge Version. THIS IS NOT A BUG!"))

            cmd = ["cmd.exe", "/c", "run.bat"]

            # Start the subprocess
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.server_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            # Start monitoring the process
            self.monitor.process = self.process
            monitor_task = asyncio.create_task(self.monitor.run())

            # Start tasks for reading output and taking input
            output_task = asyncio.create_task(self._console_reader())
            # input_task = asyncio.create_task(self.console_writer())

            # Wait for the server process to finish
            await self.process.wait()

            self.running = False

            # Cancel input and output tasks once the server stops
            await asyncio.gather(output_task, return_exceptions=True)
            await asyncio.gather(monitor_task, return_exceptions=True)

        except FileNotFoundError as e:
            print(f"Error: {e}")

        except Exception as e:
            print(f"An error occurred: {e}")

        finally:
            self.starting = False
            self.running = False

    async def stop(self):
        """
        Stops the server. Same as regular stop but
        without waiting for the process to finish.
        """
        if self.process and self.running:
            print("Stopping the server...")
            self.running = False
            self.stopping = True
            try:
                # Send the 'stop' command to the server
                if self.process.stdin:
                    self.process.stdin.write(b"stop\n")
                    await self.process.stdin.drain()

                print("Server stopped.")
            except Exception as e:
                print(f"Error while stopping the server: {e}")
            finally:
                # Ensure process cleanup
                self.process = None
                self.running = False
                self.stopping = False
                self.monitor.stop()
        else:
            print("Server is not running.")

    def _create_server(self):
        """
        Creates the server
        """
        # Create folder and download jar
        self._create_server_folder()
        self._download_jar()

        # Additional setup for Forge servers
        self._init_forge_server()
        self._set_user_jvm_args()

        # Complete by accepting EULA and saving
        self.accept_eula()
        self.save()
