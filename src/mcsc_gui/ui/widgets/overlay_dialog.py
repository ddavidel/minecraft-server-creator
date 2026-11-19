"""
In-window modal dialogs (FR-024).

An :class:`OverlayDialog` covers its host (the main window's central widget)
with a dark overlay and shows a centered panel. It fades in and out, closes with
Esc (unless busy) and keeps the keyboard focus inside the panel.

Subclasses fill :attr:`body` and :attr:`buttons` (or use :meth:`add_button`).
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import icon_button, label


def dialog_host(widget: QWidget) -> QWidget:
    """The widget dialogs and toasts cover: the window's central widget."""
    window = widget.window()
    if isinstance(window, QMainWindow) and window.centralWidget() is not None:
        return window.centralWidget()
    return window


def _overlay_color() -> QColor:
    return QColor(0, 0, 0, 150)


class OverlayDialog(QWidget):
    """Base class for in-window modal dialogs."""

    accepted = Signal()
    rejected = Signal()
    closed = Signal()

    def __init__(self, parent: QWidget, title: str = "", *, width: int = 520,
                 closable: bool = True) -> None:
        host = dialog_host(parent)
        super().__init__(host)
        self._host = host
        self._closable = closable
        self._busy = False
        self._closing = False
        self._result: bool | None = None
        self._anim: QPropertyAnimation | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.panel = QFrame(self)
        self.panel.setObjectName("DialogPanel")
        self.panel.setFixedWidth(width)
        self.panel.setAccessibleName(title)
        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.panel.setGraphicsEffect(shadow)
        outer.addWidget(self.panel, 0, Qt.AlignmentFlag.AlignCenter)

        s = TOKENS.spacing
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(s.xl, s.xl, s.xl, s.xl)
        panel_layout.setSpacing(s.lg)

        header = QHBoxLayout()
        header.setSpacing(s.sm)
        self.title_label: QLabel = label(title, "headline")
        header.addWidget(self.title_label, 1)
        self.close_button = icon_button("close", "Close", color=TOKENS.palette.text_muted)
        self.close_button.clicked.connect(self.reject)
        self.close_button.setVisible(closable)
        header.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        panel_layout.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(s.md)
        panel_layout.addLayout(self.body)

        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(s.sm)
        self.buttons.addStretch(1)
        panel_layout.addSpacing(s.xs)
        panel_layout.addLayout(self.buttons)

        host.installEventFilter(self)

    # ----------------------------------------------------------------- state

    @property
    def busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool) -> None:
        """While busy the dialog can't be closed with Esc or the close button."""
        self._busy = busy
        self.close_button.setEnabled(not busy)

    @property
    def result(self) -> bool | None:
        """True if accepted, False if rejected, None while open."""
        return self._result

    def add_button(self, btn: QPushButton) -> QPushButton:
        self.buttons.addWidget(btn)
        return btn

    # ------------------------------------------------------------ open/close

    def open(self) -> None:
        self.setGeometry(self._host.rect())
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.0)
        self.setGraphicsEffect(effect)
        self.show()
        self.raise_()
        self._focus_first()
        self._fade(0.0, 1.0, self._opened)

    def _opened(self) -> None:
        if not self._closing:
            self.setGraphicsEffect(None)  # nested effects are slow: keep only the panel shadow

    def accept(self) -> None:
        self._result = True
        self.accepted.emit()
        self.close_dialog()

    def reject(self) -> None:
        if self._busy:
            return
        self._result = False
        self.rejected.emit()
        self.close_dialog()

    def close_dialog(self) -> None:
        if self._closing:
            return
        self._closing = True
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(1.0)
        self.setGraphicsEffect(effect)
        self._fade(1.0, 0.0, self._finish)

    def _finish(self) -> None:
        self.hide()
        self._host.removeEventFilter(self)
        self.closed.emit()
        self.deleteLater()

    def _fade(self, start: float, end: float, done) -> None:
        if self._anim is not None:
            self._anim.stop()
        anim = QPropertyAnimation(self.graphicsEffect(), b"opacity", self)
        anim.setDuration(TOKENS.motion.fast_ms)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.finished.connect(done)
        self._anim = anim
        anim.start()

    # ------------------------------------------------------------ behaviour

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), _overlay_color())

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        host = getattr(self, "_host", None)  # unset while being built or torn down
        if host is not None and watched is host and event.type() == QEvent.Type.Resize:
            self.setGeometry(host.rect())
        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_Escape:
            if self._closable:
                self.reject()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        event.accept()  # clicks on the overlay never reach the window below

    def _focusable(self) -> list[QWidget]:
        widgets = [
            w for w in self.panel.findChildren(QWidget)
            if w.isVisibleTo(self.panel) and w.isEnabled()
            and w.focusPolicy() & Qt.FocusPolicy.TabFocus
        ]
        # Follow the panel's tab chain order
        ordered: list[QWidget] = []
        if widgets:
            start = widgets[0]
            current = start
            for _ in range(len(self.panel.findChildren(QWidget)) + 1):
                if current in widgets and current not in ordered:
                    ordered.append(current)
                current = current.nextInFocusChain()
                if current is start:
                    break
        return ordered or widgets

    def _focus_first(self) -> None:
        widgets = [w for w in self._focusable() if w is not self.close_button]
        target = widgets[0] if widgets else self
        target.setFocus(Qt.FocusReason.PopupFocusReason)

    def focusNextPrevChild(self, forward: bool) -> bool:  # noqa: N802 - Qt API
        """Focus trap: Tab cycles inside the panel."""
        widgets = self._focusable()
        if not widgets:
            return True
        current = self.focusWidget()
        try:
            index = widgets.index(current)
        except ValueError:
            index = -1 if forward else 0
        widgets[(index + (1 if forward else -1)) % len(widgets)].setFocus(
            Qt.FocusReason.TabFocusReason
        )
        return True


class MessageDialog(OverlayDialog):
    """Simple confirmation dialog: message + cancel/confirm buttons."""

    def __init__(self, parent: QWidget, title: str, message: str, *, confirm: str,
                 cancel: str, confirm_variant: str = "primary",
                 confirm_icon: str | None = "check", cancel_icon: str | None = "close") -> None:
        super().__init__(parent, title, width=460)
        from mcsc_gui.ui.widgets.common import button  # pylint: disable=import-outside-toplevel

        self.message_label = label(message, "muted", wrap=True)
        self.body.addWidget(self.message_label)
        self.cancel_button = self.add_button(button(cancel, cancel_icon))
        self.confirm_button = self.add_button(button(confirm, confirm_icon, variant=confirm_variant))
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)
        self.confirm_button.setDefault(True)
