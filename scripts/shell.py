"""
MCSC Shell. Not sure if i need this.
"""

import sys
import os
import code

sys.path.insert(0, os.path.abspath("src"))

import mcsc  # pymcsc library
import mcsc_gui

locals = {name: getattr(mcsc, name) for name in dir(mcsc) if not name.startswith("_")}
locals.update({name: getattr(mcsc_gui, name) for name in dir(mcsc_gui) if not name.startswith("_")})

code.interact(
    banner="Welcome to the MCSC shell!",
    local=locals
)
