from PySide6.QtCore import Qt

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
