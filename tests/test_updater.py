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


# ------------------------------------------------------- version check


def test_is_newer_compares_each_part_as_a_number():
    assert update.is_newer("3.2.10", "3.2.9")
    assert update.is_newer("3.3.0", "3.2.10")
    assert update.is_newer("3.2.1", "3.2")
    assert update.is_newer("3.2.1.post1", "3.2.1")
    assert update.is_newer("3.2.1", "3.2.1.dev0")
    assert not update.is_newer("3.2.0", "3.2")
    assert not update.is_newer("3.2.1", "3.2.1")
    assert not update.is_newer("3.2.0", "3.10.0")


def test_is_newer_ignores_prereleases_and_invalid_versions():
    assert not update.is_newer("4.0.0rc1", "3.2.1")  # pip --upgrade wouldn't install it
    assert not update.is_newer("latest", "3.2.1")
    assert not update.is_newer("3.3.0", "unknown")


def test_check_for_updates_uses_pypi_version():
    with mock.patch.object(update, "get_latest_version", return_value="3.10.0"), \
            mock.patch.object(update, "get_current_version", return_value="3.9.12"):
        assert update.check_for_updates()
    with mock.patch.object(update, "get_latest_version", return_value=None):
        assert not update.check_for_updates()


# ------------------------------------------------- automatic update


class _Settings:
    def __init__(self, **values):
        self.user_settings = dict(values)

    def update_settings(self, **values):
        self.user_settings.update(values)


def _auto(settings, latest="9.0.0", launched=True, installed=True):
    launch = mock.Mock(return_value=launched)
    with mock.patch.object(update, "installed_as_package", return_value=installed), \
            mock.patch.object(update, "get_current_version", return_value="3.2.1"):
        result = update.auto_update_at_startup(settings, latest_version=lambda: latest,
                                               launch=launch)
    return result, launch


def test_auto_update_starts_the_silent_updater_once_per_version():
    settings = _Settings()
    result, launch = _auto(settings)
    assert result
    launch.assert_called_once_with(silent=True)
    assert settings.user_settings["auto_update_attempted"] == "9.0.0"

    # Still on 3.2.1 at the next start: the update failed, don't loop
    result, launch = _auto(settings)
    assert not result
    launch.assert_not_called()

    # A newer release is tried again
    result, launch = _auto(settings, latest="9.0.1")
    assert result


def test_auto_update_skipped_when_up_to_date_offline_or_from_source():
    assert _auto(_Settings(), latest="3.2.1")[0] is False
    assert _auto(_Settings(), latest=None)[0] is False
    assert _auto(_Settings(), installed=False)[0] is False
    assert _auto(_Settings(), launched=False)[0] is False


def test_auto_update_never_raises():
    def offline():
        raise OSError("no network")

    with mock.patch.object(update, "installed_as_package", return_value=True):
        assert not update.auto_update_at_startup(_Settings(), latest_version=offline)


def test_installed_as_package():
    assert update.installed_as_package(r"C:\Python\Lib\site-packages\mcsc_gui\update.py")
    assert not update.installed_as_package(r"C:\repo\src\mcsc_gui\update.py")


def test_silent_flag_reaches_the_updater():
    command = update.updater_command("u.py", pid=1, launcher=None, lang="en", icon=None,
                                     log=None, relaunch=["py"], silent=True)
    assert updater.parse_args(command[3:]).silent
    assert not updater.parse_args(["--python", "p", "--package", "p", "--relaunch", "[]"]).silent


def test_headless_reopens_the_app_even_when_pip_fails():
    args = _args(relaunch=["py", "-m", "mcsc_gui", "--background"])
    with mock.patch.object(updater, "run_pip", lambda *_a: 1), \
            mock.patch.object(updater, "relaunch") as reopen:
        assert updater.run_headless(args, updater.Translator("en"), updater.Log(None)) == 1
    reopen.assert_called_once_with(["py", "-m", "mcsc_gui", "--background"])


def test_headless_doesnt_reopen_an_app_that_never_closed():
    args = _args(wait_pid=[123], relaunch=["py"])
    with mock.patch.object(updater, "wait_for_pids", return_value=False), \
            mock.patch.object(updater, "relaunch") as reopen:
        assert updater.run_headless(args, updater.Translator("en"), updater.Log(None)) == 1
    reopen.assert_not_called()


def test_relaunch_keeps_background_option():
    command = update.relaunch_command([r"C:\venv\Scripts\mcsc.exe", "--background"])
    assert command[-1] == "--background"


def test_relaunch_can_force_or_drop_background():
    argv = ["mcsc.exe", "--debug"]
    assert update.relaunch_command(argv, background=True)[-2:] == ["--debug", "--background"]
    argv.append("--background")
    assert "--background" not in update.relaunch_command(argv, background=False)
    assert update.relaunch_command(argv)[-1] == "--background"


def test_claim_auto_update_records_the_attempt():
    settings = _Settings()
    with mock.patch.object(update, "installed_as_package", return_value=True), \
            mock.patch.object(update, "get_current_version", return_value="3.2.1"):
        assert update.claim_auto_update(settings, "3.3.0")
        assert not update.claim_auto_update(settings, "3.3.0")
        assert not update.claim_auto_update(settings, "3.2.1")
        assert not update.claim_auto_update(settings, None)
    assert settings.user_settings["auto_update_attempted"] == "3.3.0"
