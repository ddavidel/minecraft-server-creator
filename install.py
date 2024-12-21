"""
MCSC Installation script
"""

import sys
import subprocess


print("\tMCSC - Minecraft Server Creator")
install = input("\nWould you like to install? [y/n] >>> ") in ["y","Y"]

if install:
    # Install requirements
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True
    )
    print("\nInstallation completed. Press ENTER to quit.")
    input()
else:
    print("\tClosing installation")
    sys.exit()
