from mcsc_gui.core import ansi, players
from mcsc_gui.core.ansi import DEFAULT, Style

ESC = "\x1b"
# A line of Paper's /help output, as in the console
HELP_LINE = (f"[21:21:52 INFO]: {ESC}[38;2;255;170;0m/teleport: {ESC}[38;2;255;255;255m"
             f"A Mojang provided command.{ESC}[0m")


def test_strip_removes_every_sequence():
    assert ansi.strip(HELP_LINE) == "[21:21:52 INFO]: /teleport: A Mojang provided command."
    assert ansi.strip(f"a{ESC}[2Kb{ESC}(Bc{ESC}") == "abc"
    assert ansi.strip("plain") == "plain"


def test_parse_truecolor_runs():
    assert ansi.parse(HELP_LINE) == [
        ("[21:21:52 INFO]: ", DEFAULT),
        ("/teleport: ", Style("#ffaa00")),
        ("A Mojang provided command.", Style("#ffffff")),
    ]


def test_parse_16_and_256_colors_and_attributes():
    runs = ansi.parse(f"{ESC}[1;93mwarn{ESC}[22;39m norm {ESC}[38;5;196mred{ESC}[4mu{ESC}[m")
    assert runs == [
        ("warn", Style(ansi.BRIGHT_COLORS[3], bold=True)),
        (" norm ", DEFAULT),
        ("red", Style("#ff0000")),
        ("u", Style("#ff0000", underline=True)),
    ]


def test_background_and_malformed_codes_are_ignored():
    assert ansi.parse(f"{ESC}[48;2;1;2;3mx{ESC}[38;2;9my") == [("x", DEFAULT), ("y", DEFAULT)]
    assert ansi.parse("") == []


def test_colored_join_line_is_detected():
    line = f"[21:30:00 INFO]: {ESC}[38;2;255;255;85mSteve joined the game{ESC}[0m"
    assert players.is_join_leave_line(line)
