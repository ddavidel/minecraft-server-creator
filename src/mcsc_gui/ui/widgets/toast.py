"""
Non-blocking toast notifications (FR-023).

Toasts stack in the bottom-right corner of a host widget (8 px gap, at most
:data:`MAX_VISIBLE`, the oldest are closed first), fade/slide in and out and
dismiss themselves after a timeout. ``progress`` toasts show a spinner and stay
until resolved through their :class:`ToastHandle`.

Only call the manager from the UI thread; other threads go through
:class:`mcsc_gui.ui.tasks.ToastNotifier`.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)
from shiboken6 import isValid

from mcsc_gui.ui.theme.icons import icon
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import icon_button
from mcsc_gui.ui.widgets.spinner import Spinner

MAX_VISIBLE = 4
GAP = 8
MARGIN = 16
WIDTH = 340

LEVELS = ("info", "success", "warning", "error", "progress")


def _level_color(level: str) -> str:
    p = TOKENS.palette
    return {
        "info": p.info,
        "success": p.success,
        "warning": p.warning,
        "error": p.danger,
        "progress": p.accent,
    }[level]


class Toast(QFrame):
    """A single toast. Created and positioned by :class:`ToastManager`."""

    closed = Signal(object)

    def __init__(self, host: QWidget, level: str, message: str) -> None:
        super().__init__(host)
        self.setObjectName("Toast")
        self.setFixedWidth(WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.level = level
        self.dismissed = False
        self._animations: list[QPropertyAnimation] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 6, 10)
        layout.setSpacing(10)

        self._icon = QLabel(self)
        self._icon.setFixedSize(20, 20)
        self._spinner = Spinner(18, parent=self)
        layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignTop)

        self._message = QLabel(message, self)
        self._message.setWordWrap(True)
        self._message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._message, 1)

        close = icon_button("close", "Close", parent=self, color=TOKENS.palette.text_muted)
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.clicked.connect(self.dismiss)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

        self.set_level(level)

    # --------------------------------------------------------------- content

    @property
    def message(self) -> str:
        return self._message.text()

    @property
    def timer_active(self) -> bool:
        return self._timer.isActive()

    def set_message(self, message: str) -> None:
        self._message.setText(message)
        self.adjustSize()

    def set_level(self, level: str) -> None:
        if level not in LEVELS:
            raise ValueError(f"Unknown toast level: {level}")
        self.level = level
        color = _level_color(level)
        p = TOKENS.palette
        b = TOKENS.borders
        self.setStyleSheet(
            f"QFrame#Toast {{ background: {p.surface_raised};"
            f" border: {b.width}px solid {color}; border-bottom: {b.bevel}px solid {color};"
            f" border-radius: {TOKENS.radii.control}px; }}"
        )
        if level == "progress":
            self._icon.hide()
            self._spinner.show()
        else:
            self._spinner.hide()
            self._icon.setPixmap(icon(level, color).pixmap(20, 20))
            self._icon.show()
        self.setAccessibleName(f"{level}: {self.message}")

    def start_timeout(self, timeout_ms: int | None) -> None:
        self._timer.stop()
        if timeout_ms:
            self._timer.start(timeout_ms)

    # ------------------------------------------------------------- animation

    def _animate(self, prop: bytes, target, start=None, duration: int | None = None,
                 on_done=None) -> None:
        obj = self.graphicsEffect() if prop == b"opacity" else self
        anim = QPropertyAnimation(obj, prop, self)
        anim.setDuration(duration or TOKENS.motion.fast_ms)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if start is not None:
            anim.setStartValue(start)
        anim.setEndValue(target)
        if on_done is not None:
            anim.finished.connect(on_done)
        anim.finished.connect(lambda a=anim: a in self._animations and self._animations.remove(a))
        self._animations.append(anim)
        anim.start()

    def _use_opacity(self, value: float) -> None:
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(value)
        self.setGraphicsEffect(effect)

    def _use_shadow(self) -> None:
        # Hard, unblurred offset: a "pixel" shadow that matches the blocky style.
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(0)
        shadow.setOffset(4, 4)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.setGraphicsEffect(shadow)

    def appear(self, pos: QPoint) -> None:
        self._use_opacity(0.0)
        self.move(pos + QPoint(24, 0))
        self.show()
        self.raise_()
        self._animate(b"pos", pos)
        self._animate(b"opacity", 1.0, 0.0, on_done=self._appeared)

    def _appeared(self) -> None:
        if not self.dismissed:
            self._use_shadow()

    def move_to(self, pos: QPoint, animate: bool = True) -> None:
        if not animate or not self.isVisible():
            self.move(pos)
            return
        self._animate(b"pos", pos)

    def dismiss(self) -> None:
        """Fade out and close (idempotent)."""
        if self.dismissed:
            return
        self.dismissed = True
        self._timer.stop()
        for anim in list(self._animations):
            anim.stop()
        self._animations.clear()
        self._use_opacity(1.0)
        self._animate(b"pos", self.pos() + QPoint(24, 0))
        self._animate(b"opacity", 0.0, 1.0, on_done=self._finish)

    def _finish(self) -> None:
        self.hide()
        self.closed.emit(self)
        self.deleteLater()


class ToastHandle:
    """Controls a toast after it has been shown (safe to use after it closed)."""

    def __init__(self, toast: Toast, manager: ToastManager) -> None:
        self._toast = toast
        self._manager = manager

    def _alive(self) -> bool:
        return isValid(self._toast) and not self._toast.dismissed

    @property
    def toast(self) -> Toast:
        return self._toast

    @property
    def is_open(self) -> bool:
        return self._alive()

    def update(self, msg: str) -> None:
        if self._alive():
            self._toast.set_message(msg)
            self._manager.relayout()

    def _resolve(self, level: str, msg: str, timeout_ms: int) -> None:
        if not self._alive():
            # Closed by the user (or pushed out of the stack): show the outcome anyway
            getattr(self._manager, level)(msg, timeout_ms)
            return
        self._toast.set_level(level)
        self._toast.set_message(msg)
        self._toast.start_timeout(timeout_ms)
        self._manager.relayout()

    def succeed(self, msg: str, timeout_ms: int = 3000) -> None:
        self._resolve("success", msg, timeout_ms)

    def fail(self, msg: str, timeout_ms: int = 5000) -> None:
        self._resolve("error", msg, timeout_ms)

    def dismiss(self) -> None:
        if self._alive():
            self._toast.dismiss()


class ToastManager(QObject):
    """Stacks toasts in the bottom-right corner of ``host``."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self._toasts: list[Toast] = []
        host.installEventFilter(self)

    @property
    def visible_toasts(self) -> list[Toast]:
        """Open toasts, oldest first."""
        return [t for t in self._toasts if isValid(t) and not t.dismissed]

    # -------------------------------------------------------------------- API

    def info(self, msg: str, timeout_ms: int = 3000) -> ToastHandle:
        return self._show("info", msg, timeout_ms)

    def success(self, msg: str, timeout_ms: int = 3000) -> ToastHandle:
        return self._show("success", msg, timeout_ms)

    def warning(self, msg: str, timeout_ms: int = 5000) -> ToastHandle:
        return self._show("warning", msg, timeout_ms)

    def error(self, msg: str, timeout_ms: int = 5000) -> ToastHandle:
        return self._show("error", msg, timeout_ms)

    def progress(self, msg: str) -> ToastHandle:
        return self._show("progress", msg, None)

    def clear(self) -> None:
        for toast in self.visible_toasts:
            toast.dismiss()

    # -------------------------------------------------------------- internals

    def _show(self, level: str, msg: str, timeout_ms: int | None) -> ToastHandle:
        toast = Toast(self._host, level, msg)
        toast.closed.connect(self._on_closed)
        toast.adjustSize()
        self._toasts.append(toast)

        # Keep at most MAX_VISIBLE: close the oldest ones
        open_toasts = self.visible_toasts
        for old in open_toasts[: max(0, len(open_toasts) - MAX_VISIBLE)]:
            old.dismiss()

        positions = self._positions()
        toast.appear(positions[toast])
        toast.start_timeout(timeout_ms)
        self.relayout(skip=toast)
        return ToastHandle(toast, self)

    def _positions(self) -> dict[Toast, QPoint]:
        positions: dict[Toast, QPoint] = {}
        x = self._host.width() - WIDTH - MARGIN
        y = self._host.height() - MARGIN
        for toast in reversed(self.visible_toasts):  # newest at the bottom
            toast.adjustSize()
            y -= toast.height()
            positions[toast] = QPoint(x, y)
            y -= GAP
        return positions

    def relayout(self, animate: bool = True, skip: Toast | None = None) -> None:
        for toast, pos in self._positions().items():
            if toast is not skip:
                toast.move_to(pos, animate)
                toast.raise_()

    def _on_closed(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self.relayout()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if watched is self._host and event.type() == QEvent.Type.Resize:
            self.relayout(animate=False)
        return False
