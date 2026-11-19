"""Server state tag: square LED + label, blinking while starting/stopping (FR-025)."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from mcsc import ServerState

from mcsc_gui.core.server_manager import status_label
from mcsc_gui.ui.theme.tokens import TOKENS

_DOT = 8
_PAD_X = 10
_GAP = 7


def state_color(state: ServerState) -> str:
    p = TOKENS.palette
    return {
        ServerState.STOPPED: p.text_muted,
        ServerState.STARTING: p.warning,
        ServerState.RUNNING: p.accent,
        ServerState.STOPPING: p.warning,
    }[ServerState(state)]


class StatusBadge(QWidget):
    """Shows a :class:`~mcsc.ServerState`."""

    def __init__(self, state: ServerState = ServerState.STOPPED,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = ServerState(state)
        self._pulse = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(1.0)
        self._anim.setKeyValueAt(0.5, 0.25)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1100)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.valueChanged.connect(self._on_pulse)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_state(state)

    @property
    def state(self) -> ServerState:
        return self._state

    @property
    def text(self) -> str:
        return status_label(self._state)

    @property
    def pulsing(self) -> bool:
        return self._anim.state() == QVariantAnimation.State.Running

    def set_state(self, state: ServerState | str) -> None:
        self._state = ServerState(state)
        if self._state in (ServerState.STARTING, ServerState.STOPPING):
            if not self.pulsing:
                self._anim.start()
        else:
            self._anim.stop()
            self._pulse = 1.0
        self.setAccessibleName(self.text)
        self.setToolTip(self.text)
        self.updateGeometry()
        self.update()

    def _on_pulse(self, value) -> None:
        self._pulse = float(value)
        self.update()

    def _tag_font(self) -> QFont:
        font = QFont(self.font())
        font.setFamilies(["Pixelify Sans", *font.families()])
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Medium)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        return font

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        metrics = QFontMetrics(self._tag_font())
        return QSize(_PAD_X * 2 + _DOT + _GAP + metrics.horizontalAdvance(self.text.upper()),
                     max(24, metrics.height() + 8))

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        # Square "block" tag: tinted fill, 2 px outline, pixel-font uppercase label.
        painter = QPainter(self)
        color = QColor(state_color(self._state))
        border_width = TOKENS.borders.width
        rect = QRectF(self.rect())

        background = QColor(color)
        background.setAlpha(38)
        painter.fillRect(rect, background)

        outline = QColor(color)
        if self._state is ServerState.STOPPED:
            outline = QColor(TOKENS.palette.border_strong)
        painter.setPen(QPen(outline, border_width, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        half = border_width / 2
        painter.drawRect(rect.adjusted(half, half, -half, -half))

        # Square "LED" that blinks while starting/stopping.
        led = QColor(color)
        led.setAlphaF(self._pulse)
        cy = rect.center().y()
        painter.fillRect(QRectF(_PAD_X, cy - _DOT / 2, _DOT, _DOT), led)

        painter.setFont(self._tag_font())
        text_color = {
            ServerState.STARTING: TOKENS.palette.warning_text,
            ServerState.STOPPING: TOKENS.palette.warning_text,
        }.get(self._state, color.name())
        painter.setPen(QColor(text_color))
        text_rect = QRectF(_PAD_X + _DOT + _GAP, 0, rect.width(), rect.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         self.text.upper())
