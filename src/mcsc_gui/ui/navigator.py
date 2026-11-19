"""
Page navigation inside the main window's ``QStackedWidget`` (FR-022).

The dashboard is persistent; detail and editor pages are created on every
navigation and destroyed when left (their ``dispose()`` is called first, then
``deleteLater``). A page can block leaving (e.g. unsaved changes) by
implementing ``can_leave() -> bool`` and ``confirm_leave(proceed)``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget
from shiboken6 import isValid

from mcsc_gui.ui.theme.tokens import TOKENS

logger = logging.getLogger(__name__)

DASHBOARD = "dashboard"
SERVER = "server"
EDITOR = "editor"


@dataclass(frozen=True)
class Route:
    kind: str
    args: tuple[str, ...] = ()


PageFactory = Callable[[Route], QWidget | None]


class Navigator(QObject):
    page_changed = Signal(str)  # route kind

    def __init__(self, stack: QStackedWidget, dashboard: QWidget, factory: PageFactory,
                 parent: QObject | None = None, *, animate: bool = True) -> None:
        super().__init__(parent)
        self._stack = stack
        self._dashboard = dashboard
        self._factory = factory
        self._animate = animate
        self._history: list[Route] = [Route(DASHBOARD)]
        self._anim: QPropertyAnimation | None = None
        if stack.indexOf(dashboard) < 0:
            stack.addWidget(dashboard)
        stack.setCurrentWidget(dashboard)

    # ------------------------------------------------------------ properties

    @property
    def current_route(self) -> Route:
        return self._history[-1]

    @property
    def current_page(self) -> QWidget:
        return self._stack.currentWidget()

    @property
    def can_go_back(self) -> bool:
        return len(self._history) > 1

    @property
    def history(self) -> list[Route]:
        return list(self._history)

    # -------------------------------------------------------------- actions

    def to_dashboard(self) -> None:
        self._go(Route(DASHBOARD), mode="reset")

    def to_server(self, server_id: str) -> None:
        self._go(Route(SERVER, (server_id,)), mode="push")

    def to_editor(self, server_id: str, filename: str) -> None:
        self._go(Route(EDITOR, (server_id, filename)), mode="push")

    def back(self) -> None:
        if not self.can_go_back:
            return
        self._go(self._history[-2], mode="back")

    def reload(self) -> None:
        """Recreate the current page (e.g. after the server was renamed)."""
        if self.current_route.kind != DASHBOARD:
            self._go(self.current_route, mode="replace", force=True)

    # ------------------------------------------------------------ internals

    def _go(self, route: Route, *, mode: str, force: bool = False) -> None:
        if route == self.current_route and not force:
            return
        page = self.current_page
        can_leave = getattr(page, "can_leave", None)
        if can_leave is not None and not can_leave():
            confirm = getattr(page, "confirm_leave", None)
            if confirm is not None:
                confirm(lambda: self._navigate(route, mode))
            return
        self._navigate(route, mode)

    def _navigate(self, route: Route, mode: str) -> None:
        if route.kind == DASHBOARD:
            new_page: QWidget | None = self._dashboard
        else:
            new_page = self._factory(route)
            if new_page is None:  # e.g. the server doesn't exist anymore
                logger.warning(f"Can't open {route}")
                return

        if mode == "reset":
            self._history = [Route(DASHBOARD)]
        elif mode == "back":
            self._history.pop()
        elif mode == "replace":
            self._history[-1] = route
        else:
            self._history.append(route)
        if self._history[-1] != route:
            self._history.append(route)

        old_page = self.current_page
        if new_page is not self._dashboard:
            self._stack.addWidget(new_page)
        self._stack.setCurrentWidget(new_page)
        if old_page is not self._dashboard and old_page is not new_page:
            self._destroy(old_page)
        self._fade_in(new_page)
        self.page_changed.emit(route.kind)

    def _destroy(self, page: QWidget) -> None:
        if not isValid(page):
            return
        dispose = getattr(page, "dispose", None)
        if dispose is not None:
            try:
                dispose()
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception("Error disposing a page")
        self._stack.removeWidget(page)
        page.deleteLater()

    def _fade_in(self, page: QWidget) -> None:
        if not self._animate:
            return
        if self._anim is not None:
            self._anim.stop()
        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(0.0)
        page.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(TOKENS.motion.normal_ms)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        def _done() -> None:
            if isValid(page):
                page.setGraphicsEffect(None)

        anim.finished.connect(_done)
        self._anim = anim
        anim.start()
