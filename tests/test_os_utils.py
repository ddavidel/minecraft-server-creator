import platform
import subprocess

import pytest

from mcsc_gui.core import os_utils


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows consoles")
def test_hide_child_consoles(monkeypatch):
    original = subprocess.Popen.__init__
    monkeypatch.setattr(subprocess.Popen, "__init__", original)  # restored after the test
    monkeypatch.setattr(os_utils, "_has_console", lambda: False)
    seen = []

    def fake_init(self, *args, **kwargs):
        seen.append(kwargs.get("creationflags", 0))

    monkeypatch.setattr(subprocess.Popen, "__init__", fake_init)
    assert os_utils.hide_child_consoles()
    assert os_utils.hide_child_consoles()  # idempotent

    subprocess.Popen(["java"])
    subprocess.Popen(["updater"], creationflags=subprocess.DETACHED_PROCESS)
    assert seen[0] & subprocess.CREATE_NO_WINDOW
    assert seen[1] == subprocess.DETACHED_PROCESS  # explicit console choice untouched


def test_console_kept_when_app_has_one(monkeypatch):
    monkeypatch.setattr(os_utils, "_has_console", lambda: True)
    assert not os_utils.hide_child_consoles()
