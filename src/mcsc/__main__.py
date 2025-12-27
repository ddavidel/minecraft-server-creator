"""Main ahh"""
from nicegui import ui
from .main import ServerCreatorGUI



# @ui.page("/gr")
def main():
    """Start mcsc gui"""
    ServerCreatorGUI().run()
