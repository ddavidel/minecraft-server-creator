"""
UI-independent application core.

Nothing in this package may import a UI toolkit (Qt): the UI talks to
it through plain callbacks and the :mod:`~mcsc_gui.core.notifier` protocol, so
the core can be tested without a GUI.
"""
