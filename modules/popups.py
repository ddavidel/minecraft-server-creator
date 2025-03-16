"""
Popups module.
All MCSC popups will be moved here
"""

import os
import asyncio
from nicegui import ui

from modules.translations import translate as _
from modules.utils import send_notification


def popup_remove_mod(addon_name: str, path: str):
    """Remove mod confirmation popup"""

    async def remove_addon():
        n = ui.notification(
            _("Removing {name}", name=addon_name),
            spinner=True,
            timeout=0,
            type="info",
        )
        await asyncio.sleep(0.5)

        # Remove the file
        try:
            if os.path.exists(path):
                os.remove(path)
                n.message = _("{name} removed", name=addon_name)
                n.spinner = False
                n.type = "positive"
            else:
                raise ValueError(_("File {path} not found", path=path))
        except Exception as e:
            print(f"Error removing file at {path}: {e}")
            # raise ValueError(_("Something went wrong wile removing the file")) from e
            n.message = _("Something went wrong wile removing the file")
            n.type = "negative"
            n.spinner = False

        finally:
            await asyncio.sleep(1.5)
            n.dismiss()

    with ui.dialog() as popup, ui.card().classes("create-server-popup"):
        with ui.row():
            ui.label(
                _("Are you sure you want to remove {name}", name=addon_name)
            ).style("font-size: 30px")

        with ui.row():
            ui.label(_("This action is irreversible")).style("font-size: 20px")

        with ui.row():
            remove_button = ui.button(_("Remove"))
            remove_button.on_click(remove_addon)
        return popup
