"""
Standalone updater window for MCSC.

The app copies this file to a temporary folder and runs it as a separate
process right before quitting (see :func:`mcsc_gui.update.launch_updater`).
The updater:

1. waits until the app (and its ``mcsc.exe`` launcher, if any) has exited, so
   that no file of the package is open any more;
2. runs ``pip install --upgrade`` showing pip's output in a small window;
3. reopens the app when the user clicks the button.

With ``--silent`` (automatic update at startup) there is no window: the
updater reopens the app as soon as pip is done, also when pip fails, so the
app always opens, on the new version or on the one already installed.

It must only use the standard library: it never imports ``mcsc_gui`` or
PySide6, otherwise it would keep open the very files pip has to replace. The
window is drawn with tkinter, which lives in the Python installation and is
never touched by pip.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable

WAIT_TIMEOUT = 180  # seconds to wait for the app to close
IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

TRANSLATIONS = {
    "it": {
        "Updating Minecraft Server Creator": "Aggiornamento di Minecraft Server Creator",
        "Waiting for the app to close…": "In attesa della chiusura dell'app…",
        "Downloading and installing the update…": "Download e installazione dell'aggiornamento…",
        "Update complete": "Aggiornamento completato",
        "Version {version} is installed.": "La versione {version} è installata.",
        "The app is up to date.": "L'app è aggiornata.",
        "Update failed": "Aggiornamento non riuscito",
        "pip exited with code {code}. See the details below.":
            "pip è terminato con codice {code}. Vedi i dettagli qui sotto.",
        "The app is still running. Close it and try again.":
            "L'app è ancora in esecuzione. Chiudila e riprova.",
        "Can't start pip: {error}": "Impossibile avviare pip: {error}",
        "Open Minecraft Server Creator": "Apri Minecraft Server Creator",
        "Retry": "Riprova",
        "Close": "Chiudi",
        "Please wait until the update is finished.":
            "Attendi la fine dell'aggiornamento.",
    },
}

COLORS = {
    "background": "#1c1f26",
    "surface": "#12141a",
    "border": "#343a4a",
    "text": "#f0ede6",
    "muted": "#a39f95",
    "accent": "#5bbf3a",
    "accent_hover": "#6bcc4a",
    "accent_text": "#0f1a0a",
    "danger": "#ff8a8d",
    "secondary": "#2b303c",
}


class Translator:
    def __init__(self, lang: str) -> None:
        self.table = TRANSLATIONS.get(lang, {})

    def __call__(self, message: str, **kwargs) -> str:
        text = self.table.get(message, message)
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text


# ------------------------------------------------------------------ logic


def pid_alive(pid: int) -> bool:
    """True if a process with this PID is still running."""
    if pid <= 0:
        return False
    if IS_WINDOWS:
        import ctypes  # pylint: disable=import-outside-toplevel

        kernel32 = ctypes.windll.kernel32
        synchronize = 0x00100000
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            # WAIT_TIMEOUT (0x102) means the process hasn't exited yet
            return kernel32.WaitForSingleObject(handle, 0) == 0x102
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_pids(pids: Iterable[int], timeout: float = WAIT_TIMEOUT,
                  alive: Callable[[int], bool] = pid_alive,
                  sleep: Callable[[float], None] = time.sleep) -> bool:
    """Wait until every PID has exited. Returns False on timeout."""
    pending = [pid for pid in pids if pid > 0]
    deadline = time.monotonic() + timeout
    while True:
        pending = [pid for pid in pending if alive(pid)]
        if not pending:
            return True
        if time.monotonic() >= deadline:
            return False
        sleep(0.25)


def pip_command(python: str, package: str) -> list[str]:
    return [python, "-m", "pip", "install", "--upgrade", "--no-input",
            "--disable-pip-version-check", package]


def installed_version(output: str, package: str) -> str | None:
    """The version pip reports as installed ("Successfully installed pkg-1.2.3")."""
    for line in output.splitlines():
        if not line.startswith("Successfully installed"):
            continue
        for item in line.split()[2:]:
            name, _, ver = item.rpartition("-")
            if re.sub(r"[-_.]+", "-", name).lower() == re.sub(r"[-_.]+", "-", package).lower():
                return ver
    return None


def no_window_flags() -> int:
    return CREATE_NO_WINDOW if IS_WINDOWS else 0


def run_pip(python: str, package: str, on_line: Callable[[str], None]) -> int:
    """Run pip streaming its output line by line; returns the exit code."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    with subprocess.Popen(
        pip_command(python, package),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", env=env,
        cwd=os.path.expanduser("~"), creationflags=no_window_flags(),
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            on_line(line.rstrip("\r\n"))
        return process.wait()


def relaunch(command: list[str]) -> None:
    """Start the app detached from the updater."""
    kwargs: dict = {
        "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL, "cwd": os.path.expanduser("~"), "close_fds": True,
    }
    if not IS_WINDOWS:
        subprocess.Popen(command, start_new_session=True, **kwargs)  # pylint: disable=consider-using-with
        return
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    try:
        subprocess.Popen(command, creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, **kwargs)  # pylint: disable=consider-using-with
    except OSError:  # the job doesn't allow breakaway
        subprocess.Popen(command, creationflags=flags, **kwargs)  # pylint: disable=consider-using-with


class Log:
    """Appends to the updater log file, never raising."""

    def __init__(self, path: str | None) -> None:
        self.path = path

    def write(self, line: str) -> None:
        if not self.path:
            return
        try:
            with open(self.path, "a", encoding="utf-8") as file:
                file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
        except OSError:
            pass


# ------------------------------------------------------------------- work


class UpdateJob:
    """Runs the update in a thread, reporting events through a queue."""

    def __init__(self, args: argparse.Namespace, tr: Translator, log: Log) -> None:
        self.args = args
        self.tr = tr
        self.log = log
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.timed_out = False  # the app never closed: don't reopen it

    def start(self) -> None:
        threading.Thread(target=self.run, daemon=True).start()

    def emit(self, kind: str, text: str = "") -> None:
        self.events.put((kind, text))

    def run(self) -> None:
        tr = self.tr
        self.emit("status", tr("Waiting for the app to close…"))
        if not wait_for_pids(self.args.wait_pid or []):
            self.log.write("Timed out waiting for the app to close")
            self.timed_out = True
            self.emit("failed", tr("The app is still running. Close it and try again."))
            return

        self.emit("status", tr("Downloading and installing the update…"))
        lines: list[str] = []

        def on_line(line: str) -> None:
            lines.append(line)
            self.log.write(line)
            self.emit("line", line)

        try:
            code = run_pip(self.args.python, self.args.package, on_line)
        except OSError as e:
            self.log.write(f"Can't start pip: {e}")
            self.emit("failed", tr("Can't start pip: {error}", error=e))
            return
        self.log.write(f"pip exited with code {code}")
        if code != 0:
            self.emit("failed", tr("pip exited with code {code}. See the details below.", code=code))
            return
        version = installed_version("\n".join(lines), self.args.package)
        if version:
            self.emit("done", tr("Version {version} is installed.", version=version))
        else:
            self.emit("done", tr("The app is up to date."))


# --------------------------------------------------------------------- UI


class UpdaterWindow:  # pragma: no cover - needs a display
    def __init__(self, args: argparse.Namespace, tr: Translator, log: Log) -> None:
        import tkinter as tk  # pylint: disable=import-outside-toplevel
        from tkinter import font as tkfont  # pylint: disable=import-outside-toplevel
        from tkinter import ttk  # pylint: disable=import-outside-toplevel

        self.tk = tk
        self.args = args
        self.tr = tr
        self.log = log
        self.job: UpdateJob | None = None
        self.busy = False

        root = self.root = tk.Tk()
        root.title(tr("Updating Minecraft Server Creator"))
        root.configure(bg=COLORS["background"])
        root.geometry("560x400")
        root.minsize(440, 320)
        if args.icon:
            try:
                root.iconbitmap(args.icon)
            except tk.TclError:
                pass
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        base = tkfont.nametofont("TkDefaultFont").actual("family")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Bar.Horizontal.TProgressbar", troughcolor=COLORS["surface"],
                        background=COLORS["accent"], bordercolor=COLORS["border"],
                        lightcolor=COLORS["accent"], darkcolor=COLORS["accent"], thickness=10)

        frame = tk.Frame(root, bg=COLORS["background"], padx=20, pady=18)
        frame.pack(fill="both", expand=True)

        self.title = tk.Label(frame, text=tr("Updating Minecraft Server Creator"),
                              bg=COLORS["background"], fg=COLORS["text"],
                              font=(base, 13, "bold"), anchor="w")
        self.title.pack(fill="x")
        self.status = tk.Label(frame, text="", bg=COLORS["background"], fg=COLORS["muted"],
                               font=(base, 10), anchor="w", justify="left", wraplength=500)
        self.status.pack(fill="x", pady=(4, 12))

        self.progress = ttk.Progressbar(frame, mode="indeterminate",
                                        style="Bar.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(0, 12))

        log_frame = tk.Frame(frame, bg=COLORS["border"], padx=1, pady=1)
        log_frame.pack(fill="both", expand=True)
        self.output = tk.Text(log_frame, bg=COLORS["surface"], fg=COLORS["muted"],
                              insertbackground=COLORS["text"], relief="flat", wrap="word",
                              font=("Consolas" if IS_WINDOWS else "Courier", 9),
                              padx=8, pady=6, height=8, state="disabled", highlightthickness=0)
        scroll = ttk.Scrollbar(log_frame, command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)

        buttons = tk.Frame(frame, bg=COLORS["background"])
        buttons.pack(fill="x", pady=(14, 0))
        self.open_button = self._button(buttons, tr("Open Minecraft Server Creator"),
                                        self.on_open, primary=True)
        self.retry_button = self._button(buttons, tr("Retry"), self.start)
        self.close_button = self._button(buttons, tr("Close"), self.root.destroy)

        root.update_idletasks()
        x = (root.winfo_screenwidth() - root.winfo_width()) // 2
        y = (root.winfo_screenheight() - root.winfo_height()) // 3
        root.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _button(self, parent, text: str, command, *, primary: bool = False):
        bg = COLORS["accent"] if primary else COLORS["secondary"]
        fg = COLORS["accent_text"] if primary else COLORS["text"]
        active = COLORS["accent_hover"] if primary else COLORS["border"]
        return self.tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                              activebackground=active, activeforeground=fg, relief="flat",
                              bd=0, padx=14, pady=6, cursor="hand2",
                              disabledforeground=COLORS["muted"])

    def show_buttons(self, *visible) -> None:
        for btn in (self.open_button, self.retry_button, self.close_button):
            btn.pack_forget()
        for btn in visible:
            btn.pack(side="right", padx=(8, 0))

    def append(self, line: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", line + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def start(self) -> None:
        self.busy = True
        self.title.configure(text=self.tr("Updating Minecraft Server Creator"), fg=COLORS["text"])
        self.show_buttons()
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.job = UpdateJob(self.args, self.tr, self.log)
        self.job.start()
        self.root.after(100, self.poll)

    def poll(self) -> None:
        assert self.job is not None
        try:
            while True:
                kind, text = self.job.events.get_nowait()
                if kind == "status":
                    self.status.configure(text=text, fg=COLORS["muted"])
                elif kind == "line":
                    self.append(text)
                elif kind in ("done", "failed"):
                    self.finish(kind == "done", text)
                    return
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def finish(self, ok: bool, message: str) -> None:
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate", value=100 if ok else 0)
        if ok:
            self.title.configure(text=self.tr("Update complete"), fg=COLORS["accent"])
            self.status.configure(text=message, fg=COLORS["muted"])
            self.show_buttons(self.open_button, self.close_button)
            self.open_button.focus_set()
        else:
            self.title.configure(text=self.tr("Update failed"), fg=COLORS["danger"])
            self.status.configure(text=message, fg=COLORS["danger"])
            self.show_buttons(self.open_button, self.retry_button, self.close_button)
        self.root.lift()
        self.root.focus_force()

    def on_open(self) -> None:
        try:
            relaunch(self.args.relaunch)
        except OSError as e:
            self.log.write(f"Can't reopen the app: {e}")
            self.status.configure(text=str(e), fg=COLORS["danger"])
            return
        self.root.destroy()

    def on_close(self) -> None:
        if self.busy:
            self.status.configure(text=self.tr("Please wait until the update is finished."))
            return
        self.root.destroy()

    def run(self) -> None:
        self.start()
        self.root.mainloop()


def run_headless(args: argparse.Namespace, tr: Translator, log: Log) -> int:
    """No window (``--silent``, or no tkinter): update, then reopen the app."""
    job = UpdateJob(args, tr, log)
    job.run()
    ok = False
    while not job.events.empty():
        kind, text = job.events.get()
        if kind in ("status", "line", "done", "failed"):
            print(text)
        ok = ok or kind == "done"
    if job.timed_out:  # still running: reopening it would only bring it to the front
        return 1
    try:
        relaunch(args.relaunch)
    except OSError as e:
        log.write(f"Can't reopen the app: {e}")
    return 0 if ok else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCSC updater")
    parser.add_argument("--python", required=True, help="interpreter that runs pip")
    parser.add_argument("--package", required=True)
    parser.add_argument("--wait-pid", type=int, action="append",
                        help="wait for this process to exit (repeatable)")
    parser.add_argument("--relaunch", type=json.loads, required=True,
                        help="JSON list: command that reopens the app")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--icon")
    parser.add_argument("--log")
    parser.add_argument("--silent", action="store_true",
                        help="no window: reopen the app as soon as the update is done")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - needs a display
    args = parse_args(argv)
    tr = Translator(args.lang)
    log = Log(args.log)
    log.write(f"Updater started: {args.package} (waiting for {args.wait_pid})"
              f"{' silently' if args.silent else ''}")
    if args.silent:
        return run_headless(args, tr, log)
    try:
        window = UpdaterWindow(args, tr, log)
    except Exception as e:  # pylint: disable=broad-exception-caught
        # No tkinter (optional on some Python installs) or no display
        log.write(f"Can't open the updater window ({e}): updating without it")
        return run_headless(args, tr, log)
    window.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
