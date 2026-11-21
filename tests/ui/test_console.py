from PySide6.QtCore import Qt
from PySide6.QtGui import QTextFormat

from mcsc_gui.ui.widgets.console import ConsoleView


def make_console(qtbot, max_lines=300):
    console = ConsoleView(max_lines)
    console.resize(600, 300)
    qtbot.addWidget(console)
    console.show()
    return console


def test_line_limit(qtbot):
    console = make_console(qtbot, max_lines=300)
    console.append_lines(f"line {i}" for i in range(1000))
    assert console.line_count() == 300
    lines = console.log.toPlainText().splitlines()
    assert lines[0] == "line 700"
    assert lines[-1] == "line 999"


def test_autoscroll_only_when_at_bottom(qtbot):
    console = make_console(qtbot)
    console.append_lines(f"line {i}" for i in range(200))
    bar = console.log.verticalScrollBar()
    assert console.is_at_bottom()

    console.append_lines(["more"])
    assert bar.value() == bar.maximum()  # follows the output

    bar.setValue(10)  # the user scrolled up
    console.append_lines(f"new {i}" for i in range(20))
    assert bar.value() == 10
    assert not console.is_at_bottom()


def test_batch_append_preserves_order(qtbot):
    console = make_console(qtbot)
    console.append_lines(["a", "b"])
    console.append_lines(["c"])
    assert console.log.toPlainText().splitlines() == ["a", "b", "c"]


def test_ansi_colors_become_formats_not_text(qtbot):
    esc = "\x1b"
    console = make_console(qtbot, max_lines=3)
    console.append_lines([f"[21:21:52 INFO]: {esc}[38;2;255;170;0m/tp: {esc}[0mhelp"])
    console.append_lines(["plain", f"{esc}[1;31mbold red{esc}[0m", "last"])
    lines = console.log.toPlainText().splitlines()
    assert lines == ["plain", "bold red", "last"]  # escapes gone, line limit kept

    console.set_lines([f"x {esc}[38;2;255;170;0mcolored{esc}[0m y"])
    assert console.log.toPlainText() == "x colored y"
    block = console.log.document().firstBlock()
    colors = {}
    it = block.begin()
    while not it.atEnd():
        fragment = it.fragment()
        colors[fragment.text()] = fragment.charFormat().foreground().color().name()
        it += 1
    assert colors["colored"] == "#ffaa00"


def test_plain_line_after_colored_one_has_no_color(qtbot):
    # A plain batch after a colored line used to inherit its color (red error,
    # then "Saved the game" in red too)
    console = make_console(qtbot)
    console.append_lines(["[INFO]: \x1b[3;31mUnknown command\x1b[0m"])
    console.append_lines(["[INFO]: Saved the game"])
    fmt = None
    it = console.log.document().lastBlock().begin()
    while not it.atEnd():
        fmt = it.fragment().charFormat()
        it += 1
    assert fmt is not None
    assert not fmt.hasProperty(QTextFormat.Property.ForegroundBrush)
    assert not fmt.fontItalic()


def test_command_history_and_submit(qtbot):
    console = make_console(qtbot)
    sent = []
    console.command_submitted.connect(sent.append)
    edit = console.input

    for command in ("list", "  say hi  ", ""):
        edit.setText(command)
        qtbot.keyClick(edit, Qt.Key.Key_Return)
    assert sent == ["list", "say hi"]
    assert edit.text() == ""

    qtbot.keyClick(edit, Qt.Key.Key_Up)
    assert edit.text() == "say hi"
    qtbot.keyClick(edit, Qt.Key.Key_Up)
    assert edit.text() == "list"
    qtbot.keyClick(edit, Qt.Key.Key_Up)
    assert edit.text() == "list"  # stays on the oldest
    qtbot.keyClick(edit, Qt.Key.Key_Down)
    assert edit.text() == "say hi"
    qtbot.keyClick(edit, Qt.Key.Key_Down)
    assert edit.text() == ""  # back to the (empty) draft


def test_input_can_be_disabled(qtbot):
    console = make_console(qtbot)
    console.set_input_enabled(False)
    assert not console.input.isEnabled()
    assert not console.send_button.isEnabled()
