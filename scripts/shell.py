"""
MCSC Shell. Not sure if i need this.
"""

import sys
import os
import code

sys.path.insert(0, os.path.abspath("src"))

import mcsc

locals = {name: getattr(mcsc, name) for name in dir(mcsc) if not name.startswith("_")}

locals = {name: getattr(mcsc, name) for name in dir(mcsc) if not name.startswith("_")}

code.interact(
    banner="Welcome to the MCSC shell!",
    local=locals
)
