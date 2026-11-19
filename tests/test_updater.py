"""The standalone updater and the code that starts it."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from mcsc_gui import update, updater


def test_updater_only_uses_the_standard_library():
    # It must not keep open (import) the files pip is going to replace
    source = Path(updater.__file__).read_text(encoding="utf-8")
    assert "mcsc_gui" not in source.split('"""', 2)[2].replace("mcsc_gui.update", "")
    assert "PySide6" not in source.split('"""', 2)[2]


def test_wait_for_pids_waits_until_every_process_is_gone():
    alive = {10: 3, 20: 1}  # PID -> number of checks it stays alive

    def is_alive(pid):
        alive[pid] -= 1
        return alive[pid] >= 0

    sleeps = []
    assert updater.wait_for_pids([10, 20, 0], alive=is_alive, sleep=sleeps.append)
    assert len(sleeps) == 3


def test_wait_for_pids_times_out():
    assert not updater.wait_for_pids([10], timeout=0, alive=lambda _pid: True,
                                     sleep=lambda _s: None)


def test_current_process_is_alive_and_dead_pid_is_not():
    import os  # pylint: disable=import-outside-toplevel

    assert updater.pid_alive(os.getpid())
    process = subprocess.Popen([sys.executable, "-c", "pass"])  # pylint: disable=consider-using-with
    process.wait()
    assert not updater.pid_alive(process.pid)


def test_installed_version_from_pip_output():
    output = ("Collecting minecraft-server-creator\n"
              "Successfully installed minecraft_server_creator-2.2.0 pymcsc-0.2.0\n")
    assert updater.installed_version(output, "minecraft-server-creator") == "2.2.0"
    assert updater.installed_version("Requirement already satisfied", "x") is None


def test_translator_falls_back_to_english():
    assert updater.Translator("it")("Retry") == "Riprova"
    assert updater.Translator("fr")("Retry") == "Retry"
    assert updater.Translator("en")("Version {version} is installed.", version="1") == \
        "Version 1 is installed."


def _args(**kw):
    return SimpleNamespace(**{"wait_pid": [], "python": sys.executable,
                              "package": "minecraft-server-creator", **kw})


def _events(job):
    out = []
    while not job.events.empty():
        out.append(job.events.get())
    return out


def test_job_reports_success_with_version():
    job = updater.UpdateJob(_args(), updater.Translator("en"), updater.Log(None))

    def fake_pip(_python, _package, on_line):
        on_line("Successfully installed minecraft-server-creator-9.9.9")
        return 0

    with mock.patch.object(updater, "run_pip", fake_pip):
        job.run()
    events = _events(job)
    assert events[-1] == ("done", "Version 9.9.9 is installed.")
    assert ("line", "Successfully installed minecraft-server-creator-9.9.9") in events


def test_job_reports_pip_failure_and_timeout(tmp_path):
    log = tmp_path / "updater.log"
    job = updater.UpdateJob(_args(), updater.Translator("en"), updater.Log(str(log)))
    with mock.patch.object(updater, "run_pip", lambda *_a: 1):
        job.run()
    assert _events(job)[-1][0] == "failed"
    assert "pip exited with code 1" in log.read_text(encoding="utf-8")

    job = updater.UpdateJob(_args(wait_pid=[123]), updater.Translator("en"), updater.Log(None))
    with mock.patch.object(updater, "wait_for_pids", return_value=False), \
            mock.patch.object(updater, "run_pip") as pip:
        job.run()
    pip.assert_not_called()
    assert _events(job)[-1][0] == "failed"


def test_parse_args_reads_relaunch_json():
    args = updater.parse_args(["--python", "py", "--package", "p", "--wait-pid", "1",
                               "--wait-pid", "2", "--relaunch", '["a", "-m", "b"]'])
    assert args.wait_pid == [1, 2]
    assert args.relaunch == ["a", "-m", "b"]


# ------------------------------------------------------------ app side


def test_relaunch_command_keeps_options(tmp_path):
    command = update.relaunch_command([r"C:\venv\Scripts\mcsc.exe", "--debug", "extra"])
    assert command[1:] == ["-m", "mcsc_gui", "--debug"]

    script = tmp_path / "start.py"
    script.write_text("", encoding="utf-8")
    assert update.relaunch_command([str(script)])[1:] == [str(script.resolve())]


def test_updater_command_waits_for_app_and_launcher():
    command = update.updater_command("u.py", pid=11, launcher=22, lang="it",
                                     icon=None, log="l.log", relaunch=["py", "-m", "mcsc_gui"])
    assert command[1:3] == ["-I", "u.py"]
    args = updater.parse_args(command[3:])
    assert args.wait_pid == [11, 22]
    assert args.relaunch == ["py", "-m", "mcsc_gui"]
    assert args.lang == "it" and args.log == "l.log"
    assert args.package == "minecraft-server-creator"


def test_launch_updater_runs_a_copy(tmp_path):
    with mock.patch.object(update, "UPDATER_DIR", str(tmp_path / "upd")), \
            mock.patch.object(update, "LOG_DIR_PATH", str(tmp_path / "logs")), \
            mock.patch.object(update, "_spawn_detached") as spawn:
        assert update.launch_updater()
    command = spawn.call_args.args[0]
    copy = Path(command[2])
    assert copy.parent == tmp_path / "upd"
    assert copy.read_text(encoding="utf-8") == Path(updater.__file__).read_text(encoding="utf-8")
    assert json.loads(command[command.index("--relaunch") + 1])


def test_launch_updater_failure_returns_false(tmp_path):
    with mock.patch.object(update, "UPDATER_DIR", str(tmp_path)), \
            mock.patch.object(update, "_spawn_detached", side_effect=OSError("nope")):
        assert not update.launch_updater()


def test_launcher_pid_skips_venv_redirectors():
    images = {2: r"C:\venv\Scripts\python.exe", 3: r"C:\venv\Scripts\mcsc.exe",
              4: r"C:\Windows\explorer.exe"}
    parents = {1: 2, 2: 3, 3: 4}
    assert update.launcher_pid(1, parents, images.get) == 3
    # Started with `python -m mcsc_gui` from a terminal: no launcher
    images[3] = r"C:\Windows\System32\cmd.exe"
    assert update.launcher_pid(1, parents, images.get) is None
