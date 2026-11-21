"""Dashboard: the user's servers as a responsive grid of cards (US1)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from mcsc import MinecraftServer

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.tasks import run_task
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import button, label
from mcsc_gui.ui.widgets.empty_state import EmptyState
from mcsc_gui.ui.widgets.server_card import ServerCard


class ResponsiveGrid(QWidget):
    """Grid whose column count follows the available width."""

    def __init__(self, min_item_width: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min_width = min_item_width
        self._items: list[QWidget] = []
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(TOKENS.spacing.lg)
        # An explicit minimum overrides the layout's (columns x card width): without
        # it the scroll area could never shrink the grid, so it would never reflow.
        self.setMinimumWidth(min_item_width)

    @property
    def items(self) -> list[QWidget]:
        return list(self._items)

    @property
    def columns(self) -> int:
        return self._columns

    def add(self, widget: QWidget) -> None:
        self._items.append(widget)
        self._relayout(force=True)

    def remove(self, widget: QWidget) -> None:
        if widget in self._items:
            self._items.remove(widget)
            self._grid.removeWidget(widget)
            widget.deleteLater()
            self._relayout(force=True)

    def _column_count(self) -> int:
        gap = self._grid.horizontalSpacing()
        return max(1, (self.width() + gap) // (self._min_width + gap))

    def _relayout(self, force: bool = False) -> None:
        columns = self._column_count()
        if columns == self._columns and not force:
            return
        self._columns = columns
        for widget in self._items:
            self._grid.removeWidget(widget)
        for index, widget in enumerate(self._items):
            self._grid.addWidget(widget, index // columns, index % columns)
        for column in range(self._grid.columnCount()):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)
        self._grid.setRowStretch(self._grid.rowCount(), 1)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._relayout()


class DashboardPage(QWidget):
    """Persistent page. Updates itself from :class:`ServerEvents` (no refresh button)."""

    open_server = Signal(str)
    new_server_requested = Signal()
    import_server_requested = Signal()
    # Context menu of a card (server_id)
    edit_server = Signal(str)
    clone_server = Signal(str)
    delete_server = Signal(str)

    def __init__(self, events: ServerEvents,
                 servers: Callable[[], list[MinecraftServer]] = sm.get_servers,
                 find: Callable[[str], MinecraftServer | None] = sm.find_server,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self._events = events
        self._find = find
        self._cards: dict[str, ServerCard] = {}
        s = TOKENS.spacing

        root = QVBoxLayout(self)
        root.setContentsMargins(s.xxl, s.xl, s.xxl, s.xl)
        root.setSpacing(s.xl)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = label(_("Your servers"), "display")
        # The header must not force a minimum page width: the grid reflows instead
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        titles.addWidget(self.title_label)
        self.count_label = label("", "muted")
        titles.addWidget(self.count_label)
        header.addLayout(titles, 1)
        self.new_button = button(_("New server"), "add", variant="primary",
                                 tooltip=_("New server") + " (Ctrl+N)")
        self.new_button.clicked.connect(self.new_server_requested)
        self.import_button = button(_("Import server"), "import")
        self.import_button.clicked.connect(self.import_server_requested)
        header.addWidget(self.import_button)
        header.addWidget(self.new_button)
        root.addLayout(header)

        self._content = QStackedLayout()
        root.addLayout(self._content, 1)

        self.grid = ResponsiveGrid(ServerCard.MIN_WIDTH)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.grid)
        self._content.addWidget(scroll)

        create = button(_("Create Server"), "add", variant="primary")
        create.clicked.connect(self.new_server_requested)
        import_existing = button(_("Import server"), "import")
        import_existing.clicked.connect(self.import_server_requested)
        empty_actions = QWidget()
        empty_row = QHBoxLayout(empty_actions)
        empty_row.setContentsMargins(0, 0, 0, 0)
        empty_row.setSpacing(s.sm)
        empty_row.addWidget(import_existing)
        empty_row.addWidget(create)
        self.empty_state = EmptyState(
            "splitscreen",
            _("No servers yet"),
            _("Seems like you don't have any. Let's create one!"),
            action=empty_actions,
        )
        self._content.addWidget(self.empty_state)

        for server in servers():
            self._add_card(server)
        self._update_empty()

        events.state_changed.connect(self._on_state_changed)
        events.server_added.connect(self._on_server_added)
        events.server_removed.connect(self._on_server_removed)
        events.server_updated.connect(self._on_server_updated)
        events.busy_changed.connect(self._on_server_updated)

    # ----------------------------------------------------------------- cards

    @property
    def cards(self) -> dict[str, ServerCard]:
        return dict(self._cards)

    def _add_card(self, server: MinecraftServer) -> None:
        if server.id in self._cards:
            return
        card = ServerCard(server)
        card.open_requested.connect(self.open_server)
        card.start_requested.connect(self._start)
        card.stop_requested.connect(self._stop)
        card.edit_requested.connect(self.edit_server)
        card.clone_requested.connect(self.clone_server)
        card.delete_requested.connect(self.delete_server)
        self._cards[server.id] = card
        self.grid.add(card)

    def _update_empty(self) -> None:
        count = len(self._cards)
        self._content.setCurrentIndex(0 if count else 1)
        self.count_label.setText(_("{count} servers", count=count) if count != 1
                                 else _("1 server"))
        self.count_label.setVisible(bool(count))

    # ---------------------------------------------------------------- events

    def _on_state_changed(self, server_id: str, _old: str, _new: str) -> None:
        card = self._cards.get(server_id)
        if card is not None:
            card.refresh()

    def _on_server_updated(self, server_id: str) -> None:
        self._on_state_changed(server_id, "", "")

    def _on_server_added(self, server_id: str) -> None:
        server = self._find(server_id)
        if server is not None:
            self._add_card(server)
            self._update_empty()

    def _on_server_removed(self, server_id: str) -> None:
        card = self._cards.pop(server_id, None)
        if card is not None:
            self.grid.remove(card)
            self._update_empty()

    # --------------------------------------------------------------- actions

    def _start(self, server_id: str) -> None:
        card = self._cards.get(server_id)
        if card is None:
            return
        run_task(sm.start_server(card.server), disable=[card.start_button],
                 on_success=lambda _r: card.refresh())

    def _stop(self, server_id: str) -> None:
        card = self._cards.get(server_id)
        if card is None:
            return
        run_task(sm.stop_server(card.server), disable=[card.stop_button],
                 on_success=lambda _r: card.refresh())
