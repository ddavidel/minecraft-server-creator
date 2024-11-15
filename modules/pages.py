"""
Pages
"""
from nicegui import ui

@ui.page("/", title="Server Creator - Home")
def home():
    """Home page"""
    ui.label("You are in home page.")

@ui.page("/create", title="Create Server")
def create_server():
    """Create Server page"""
    ui.label("You are in create server page.")
