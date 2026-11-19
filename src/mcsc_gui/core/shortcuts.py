"""
App shortcuts: desktop + Start menu (Windows) / applications menu (Linux).

The shortcut starts the app with ``pythonw -m mcsc_gui`` (no console window)
and uses an icon copied into the app data folder, so it keeps working when the
package is reinstalled or updated. macOS is not supported (it would need an
``.app`` bundle).
"""

from __future__ import annotations

import base64
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from appdirs import user_data_dir

from mcsc_gui.utils import get_static_path

logger = logging.getLogger(__name__)

SHORTCUT_NAME = "Minecraft Server Creator"
SHORTCUT_COMMENT = "Create and manage Minecraft servers"
# Windows taskbar identity: the running process and its shortcuts share it, so
# the taskbar shows the MCSC icon and pinning the window relaunches the app.
APP_USER_MODEL_ID = "mcsc.MinecraftServerCreator"
LINUX_DESKTOP_FILE = "mcsc.desktop"

_CSIDL_PROGRAMS = 0x0002  # Start menu > Programs
_CSIDL_DESKTOPDIRECTORY = 0x0010
_CREATE_NO_WINDOW = 0x08000000


class ShortcutError(RuntimeError):
    """The shortcut couldn't be created."""


def is_supported() -> bool:
    return platform.system() in {"Windows", "Linux"}


# ------------------------------------------------------------------ paths

def _windows_folder(csidl: int) -> Path | None:
    """Real path of a shell folder (follows OneDrive/redirected Desktops)."""
    import ctypes  # pylint: disable=import-outside-toplevel

    buffer = ctypes.create_unicode_buffer(260)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer)
    if result != 0 or not buffer.value:
        return None
    return Path(buffer.value)


def _linux_desktop_dir() -> Path:
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True,
                             timeout=5, check=False).stdout.strip()
        if out:
            return Path(out)
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / "Desktop"


def _linux_applications_dir() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "applications"


def desktop_shortcut_path() -> Path | None:
    system = platform.system()
    if system == "Windows":
        folder = _windows_folder(_CSIDL_DESKTOPDIRECTORY)
        return folder / f"{SHORTCUT_NAME}.lnk" if folder else None
    if system == "Linux":
        return _linux_desktop_dir() / LINUX_DESKTOP_FILE
    return None


def menu_shortcut_path() -> Path | None:
    system = platform.system()
    if system == "Windows":
        folder = _windows_folder(_CSIDL_PROGRAMS)
        return folder / f"{SHORTCUT_NAME}.lnk" if folder else None
    if system == "Linux":
        return _linux_applications_dir() / LINUX_DESKTOP_FILE
    return None


def desktop_shortcut_exists() -> bool:
    try:
        path = desktop_shortcut_path()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Can't locate the desktop folder")
        return False
    return bool(path and path.exists())


# ---------------------------------------------------------------- target

def launch_command() -> tuple[str, list[str]]:
    """Executable + arguments that start the app without a console window."""
    executable = Path(sys.executable)
    if platform.system() == "Windows":
        windowed = executable.with_name("pythonw.exe")
        if windowed.exists():
            executable = windowed
    return str(executable), ["-m", "mcsc_gui"]


def _install_icon() -> Path:
    """Copy the icon into the app data folder (stable across reinstalls)."""
    name = "logo.ico" if platform.system() == "Windows" else "logo-512.png"
    target = Path(user_data_dir("mcsc")) / "icons" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with get_static_path(name).open("rb") as src, open(target, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return target


# --------------------------------------------------------------- Windows

# IShellLink + IPropertyStore: WScript.Shell can't set the AppUserModelID.
_WINDOWS_SCRIPT = r'''
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

namespace Mcsc {
  [ComImport, Guid("000214F9-0000-0000-C000-000000000046"),
   InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellLinkW {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int c, IntPtr d, int fl);
    void GetIDList(out IntPtr p);
    void SetIDList(IntPtr p);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder n, int c);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string n);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder d, int c);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string d);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder a, int c);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string a);
    void GetHotkey(out short h);
    void SetHotkey(short h);
    void GetShowCmd(out int s);
    void SetShowCmd(int s);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder p, int c, out int i);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string p, int i);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string p, int r);
    void Resolve(IntPtr h, int f);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string f);
  }

  [StructLayout(LayoutKind.Sequential, Pack = 4)]
  struct PropertyKey { public Guid fmtid; public uint pid; }

  [StructLayout(LayoutKind.Explicit, Size = 24)]
  struct PropVariant {
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr pointer;
  }

  [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),
   InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IPropertyStore {
    void GetCount(out uint c);
    void GetAt(uint i, out PropertyKey k);
    void GetValue(ref PropertyKey k, IntPtr v);
    void SetValue(ref PropertyKey k, ref PropVariant v);
    void Commit();
  }

  [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
  class ShellLink { }

  public static class Shortcut {
    public static void Create(string path, string target, string args, string workDir,
                              string icon, string description, string appId) {
      IShellLinkW link = (IShellLinkW)new ShellLink();
      link.SetPath(target);
      link.SetArguments(args);
      link.SetWorkingDirectory(workDir);
      link.SetIconLocation(icon, 0);
      link.SetDescription(description);

      IPropertyStore store = (IPropertyStore)link;
      PropertyKey key = new PropertyKey();
      key.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
      key.pid = 5;  // PKEY_AppUserModel_ID
      PropVariant value = new PropVariant();
      value.vt = 31;  // VT_LPWSTR
      value.pointer = Marshal.StringToCoTaskMemUni(appId);
      try {
        store.SetValue(ref key, ref value);
        store.Commit();
      } finally {
        Marshal.FreeCoTaskMem(value.pointer);
      }
      ((IPersistFile)link).Save(path, true);
    }
  }
}
"@
[Mcsc.Shortcut]::Create($env:MCSC_LNK_PATH, $env:MCSC_LNK_TARGET, $env:MCSC_LNK_ARGS,
                        $env:MCSC_LNK_WORKDIR, $env:MCSC_LNK_ICON, $env:MCSC_LNK_DESCRIPTION,
                        $env:MCSC_LNK_APPID)
'''


def _windows_arguments(args: list[str]) -> str:
    return subprocess.list2cmdline(args)


def _create_windows_shortcut(path: Path, icon: Path) -> None:
    target, args = launch_command()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Values travel as environment variables: no quoting issues with odd paths
    env = dict(os.environ)
    env.update({
        "MCSC_LNK_PATH": str(path),
        "MCSC_LNK_TARGET": target,
        "MCSC_LNK_ARGS": _windows_arguments(args),
        "MCSC_LNK_WORKDIR": str(Path.home()),
        "MCSC_LNK_ICON": str(icon),
        "MCSC_LNK_DESCRIPTION": SHORTCUT_COMMENT,
        "MCSC_LNK_APPID": APP_USER_MODEL_ID,
    })
    encoded = base64.b64encode(_WINDOWS_SCRIPT.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", encoded],
        env=env, capture_output=True, text=True, timeout=60, check=False,
        creationflags=_CREATE_NO_WINDOW,
    )
    if result.returncode != 0 or not path.exists():
        detail = (result.stderr or result.stdout or "").strip()
        logger.error(f"Shortcut creation failed ({result.returncode}): {detail}")
        raise ShortcutError(f"Can't create the shortcut {path}")


def set_windows_app_id() -> None:
    """Give the running process the same taskbar identity as its shortcuts."""
    if platform.system() != "Windows":
        return
    try:
        import ctypes  # pylint: disable=import-outside-toplevel

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Can't set the AppUserModelID")


# ----------------------------------------------------------------- Linux

def _desktop_exec_quote(arg: str) -> str:
    """Quote an argument for the ``Exec`` key of a .desktop file."""
    if arg and not any(c in arg for c in ' \t\n"\'\\><~|&;$*?#()`'):
        return arg
    escaped = "".join("\\" + c if c in '"`$\\' else c for c in arg)
    return f'"{escaped}"'


def desktop_entry(icon: Path) -> str:
    target, args = launch_command()
    command = " ".join(_desktop_exec_quote(a) for a in [target, *args]).replace("%", "%%")
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={SHORTCUT_NAME}\n"
        f"Comment={SHORTCUT_COMMENT}\n"
        f"Exec={command}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Game;Utility;\n"
        "StartupWMClass=mcsc\n"
    )


def _create_linux_shortcut(path: Path, icon: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(desktop_entry(icon), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    # GNOME only launches desktop icons marked as trusted (best effort)
    if shutil.which("gio"):
        subprocess.run(["gio", "set", str(path), "metadata::trusted", "true"],
                       capture_output=True, timeout=5, check=False)


# ------------------------------------------------------------------- API

def create_shortcuts(*, desktop: bool = True, menu: bool = True) -> list[Path]:
    """Create (or refresh) the shortcuts. Returns the created files."""
    if not is_supported():
        raise ShortcutError(f"Shortcuts are not supported on {platform.system()}")
    targets = []
    if desktop:
        targets.append(desktop_shortcut_path())
    if menu:
        targets.append(menu_shortcut_path())
    targets = [t for t in targets if t is not None]
    if not targets:
        raise ShortcutError("Can't locate the desktop folder")

    icon = _install_icon()
    create = (_create_windows_shortcut if platform.system() == "Windows"
              else _create_linux_shortcut)
    created = []
    for path in targets:
        create(path, icon)
        logger.info(f"Shortcut created: {path}")
        created.append(path)
    return created
