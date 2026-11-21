import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

from mcsc_gui.core.changelog import read_changelog

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "draft_changelog.py"
_spec = importlib.util.spec_from_file_location("draft_changelog", SCRIPT)
draft = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = draft  # dataclasses look the module up
_spec.loader.exec_module(draft)


def commits(*subjects):
    return [c for c in (draft.parse_commit(s) for s in subjects) if c is not None]


def test_parse_commit():
    c = draft.parse_commit("feat(servers): clone a server from the dashboard context menu (#37)")
    assert (c.type, c.scope, c.breaking, c.pr) == ("feat", "servers", False, 37)
    assert c.subject == "clone a server from the dashboard context menu"

    c = draft.parse_commit("fix: correct title bar character in window title")
    assert (c.type, c.scope, c.pr) == ("fix", None, None)


def test_breaking_changes():
    assert draft.parse_commit("feat(api)!: drop the old config").breaking
    assert draft.parse_commit("refactor: new settings", "BREAKING CHANGE: reset them").breaking


@pytest.mark.parametrize("subject", [
    "update README.md", "Merge pull request #29 from x/y", "CI/CD: add workflows", "",
])
def test_non_conventional_commits_are_ignored(subject):
    assert draft.parse_commit(subject) is None


def test_latest_tag():
    assert draft.latest_tag(["1.2.4", "v3.0.0", "v3.0.10", "v3.0.2", "nightly"]) == "v3.0.10"
    assert draft.latest_tag(["nightly"]) is None
    assert draft.latest_tag([]) is None


def test_next_version():
    assert draft.next_version("3.0.1", commits("fix: a")) == "3.0.2"
    assert draft.next_version("3.0.1", commits("fix: a", "feat: b")) == "3.1.0"
    assert draft.next_version("3.0.1", commits("feat!: c")) == "4.0.0"
    assert draft.next_version("3.0.1", []) == "3.0.2"


def test_draft_entry_keeps_features():
    found = commits("feat(backup): backups (#35)", "fix: a bug", "chore: bump", "ci: x",
                    "docs: y", "feat(ui): new pages.", "feat: backups")
    entry = draft.draft_entry("3.1.0", found, today=date(2026, 12, 1))
    assert entry == {"version": "3.1.0", "date": "2026-12-01",
                     "highlights": {"en": ["Backups", "New pages"]}}


def test_draft_entry_fixes_only_on_request():
    found = commits("fix: a bug", "chore: bump")
    assert draft.draft_entry("3.0.2", found) is None
    entry = draft.draft_entry("3.0.2", found, include_fixes=True)
    assert entry["highlights"]["en"] == ["A bug"]


def test_insert_entry_newest_first_and_no_duplicates():
    changelog = {"schema": 1, "releases": [{"version": "3.0.1"}, {"version": "2.9.0"}]}
    result = draft.insert_entry(changelog, {"version": "3.0.10"})
    assert [r["version"] for r in result["releases"]] == ["3.0.10", "3.0.1", "2.9.0"]
    with pytest.raises(ValueError):
        draft.insert_entry(result, {"version": "3.0.10"})
    replaced = draft.insert_entry(result, {"version": "3.0.10", "new": True}, force=True)
    assert [r["version"] for r in replaced["releases"]].count("3.0.10") == 1
    assert replaced["releases"][0]["new"] is True


@pytest.fixture
def fake_git(monkeypatch):
    history = ["feat(servers): clone servers (#37)", "fix: something", "chore: release"]
    monkeypatch.setattr(draft, "last_tag", lambda: "v3.0.1")
    monkeypatch.setattr(draft, "read_commits", lambda since: commits(*history))
    monkeypatch.setattr(draft, "current_version", lambda: "3.0.1")
    return history


def test_main_writes_a_valid_changelog(tmp_path, fake_git):
    path = tmp_path / "changelog.json"
    path.write_text(json.dumps({"schema": 1, "releases": [
        {"version": "3.0.1", "date": "2026-11-20", "highlights": {"en": ["Old"]}}]}),
        encoding="utf-8")

    assert draft.main(["--file", str(path)]) == 0
    notes = read_changelog(path)
    assert [n.version for n in notes] == ["3.1.0", "3.0.1"]
    assert notes[0].items("en") == ("Clone servers",)

    # Running it again doesn't duplicate the entry
    assert draft.main(["--file", str(path)]) == 1
    assert len(read_changelog(path)) == 2


def test_main_dry_run_leaves_the_file_untouched(tmp_path, fake_git, capsys):
    path = tmp_path / "changelog.json"
    assert draft.main(["--file", str(path), "--dry-run", "--version", "v3.2.0"]) == 0
    assert not path.exists()
    assert json.loads(capsys.readouterr().out)["version"] == "3.2.0"


def test_main_nothing_to_add(tmp_path, monkeypatch, fake_git):
    fake_git[:] = ["fix: only a fix"]
    path = tmp_path / "changelog.json"
    assert draft.main(["--file", str(path)]) == 0
    assert not path.exists()
