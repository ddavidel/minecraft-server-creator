[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey)](./LICENSE)

![Demo Image](https://i.imgur.com/K0jyPsE.png)
# MCSC - Minecraft Server Creator
MCSC is a user-friendly tool written in Python with a GUI that simplifies the process of creating and managing Minecraft servers. Whether you're a beginner or experienced, MCSC allows you to easily set up, run, and control multiple Minecraft servers from a single interface.
> **Warning**: MCSC is still in development, thus it may not be completely error free.

## Features
- **Create Multiple Servers**: Set up and manage multiple Minecraft servers from within the app.
- **Start/Stop Servers**: Easily start and stop your Minecraft servers directly from the GUI.
- **Console Interaction**: Read the console output in real-time and send commands to the Minecraft server console.
- **Edit server.properties**: Customize your Minecraft server settings by editing the `server.properties` file with a built-in editor.
- **User-Friendly GUI**: A simple and intuitive interface designed for both beginners and experienced users.
- **Manage Server Instances**: Keep track of all your servers in one place.

## Installation
MCSC requires Python 3.12+ and Java.

Install it from PyPI and run it:
```bash
pip install minecraft-server-creator
mcsc
```

To run it from the source code:
1. Clone the repository:
`git clone https://github.com/ddavidel/minecraft-server-creator.git`

2. Navigate to the project folder and install it with its dependencies:
`pip install -e .`

3. Run the application with `mcsc` or `python scripts/start.py` (add `--debug` to log to the console).

## Project structure
- `src/mcsc_gui`: the desktop app (NiceGUI interface, translations, settings, telemetry, updates).
- Server management (creating, running, monitoring and configuring servers) is provided by the
  [pymcsc](https://pypi.org/project/pymcsc/) library, imported as `mcsc`.

## Upcoming Features
- **Support for more server types**: In the future updates, MCSC will support creating and managing many popular Minecraft server types.
- **Plugin and Mod Manager**: Easily manage plugins and mods.
