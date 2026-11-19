"""Build the Windows installer of Minecraft Server Creator.

    python installer/build_installer.py                 # build from this source tree
    python installer/build_installer.py --wheel X.whl   # use an already built wheel
    python installer/build_installer.py --no-compile    # prepare the files only

What it does:

1. downloads a private, relocatable Python (python-build-standalone, the same
   builds ``uv`` uses) and checks its SHA-256;
2. installs MCSC and its dependencies into it with pip;
3. compiles ``installer/mcsc.iss`` with Inno Setup (``ISCC.exe``).

The installer copies that Python into ``%LOCALAPPDATA%\\Programs`` and starts the
app with ``pythonw.exe -m mcsc_gui``. The in-app updater keeps working because
it runs ``python -m pip install --upgrade`` on the interpreter running the app,
and this Python has both pip and tkinter (the "embeddable" Python from
python.org has neither).

Windows only (the Python it bundles is a Windows build). Output:
``dist/installer/mcsc-setup-<version>.exe``.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build" / "installer"
CACHE_DIR = BUILD_DIR / "cache"
STAGE_DIR = BUILD_DIR / "stage"
OUTPUT_DIR = ROOT / "dist" / "installer"
ISS_FILE = ROOT / "installer" / "mcsc.iss"

# Pinned private Python. To update it pick a release at
# https://github.com/astral-sh/python-build-standalone/releases and copy the
# asset name and its sha256 (shown next to the asset on GitHub).
PYTHON_RELEASE = "20261026"
PYTHON_ASSET = "cpython-3.12.16+20261026-x86_64-pc-windows-msvc-install_only.tar.gz"
PYTHON_SHA256 = "590dfcbe3a34c07301e6332e13e2188b98655cd072b08afa45a7998dc4c22bc5"
PYTHON_URL = ("https://github.com/astral-sh/python-build-standalone/releases/download/"
              f"{PYTHON_RELEASE}/{PYTHON_ASSET.replace('+', '%2B')}")


def log(message: str) -> None:
    print(f"[installer] {message}", flush=True)


def run(command: list[str | Path], **kwargs) -> None:
    log("$ " + " ".join(str(part) for part in command))
    subprocess.run([str(part) for part in command], check=True, **kwargs)


def project_version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_python() -> Path:
    """Download the pinned Python archive (cached) and verify it."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    archive = CACHE_DIR / PYTHON_ASSET
    if archive.exists() and sha256(archive) == PYTHON_SHA256:
        log(f"Using cached {archive.name}")
        return archive
    log(f"Downloading {PYTHON_URL}")
    partial = archive.with_suffix(".part")
    with urllib.request.urlopen(PYTHON_URL, timeout=120) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out)
    actual = sha256(partial)
    if actual != PYTHON_SHA256:
        partial.unlink()
        raise SystemExit(f"Checksum mismatch for {PYTHON_ASSET}: got {actual}")
    partial.replace(archive)
    return archive


def extract_python(archive: Path) -> Path:
    """Extract the archive into a clean stage folder. Returns ``stage/python``."""
    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True)
    log(f"Extracting {archive.name}")
    with tarfile.open(archive) as tar:
        tar.extractall(STAGE_DIR, filter="data")
    python_dir = STAGE_DIR / "python"
    for required in ("python.exe", "pythonw.exe"):
        if not (python_dir / required).exists():
            raise SystemExit(f"{required} is missing from {archive.name}")
    return python_dir


def build_wheel(python: Path) -> Path:
    """Build the wheel of this source tree with the bundled Python."""
    wheel_dir = BUILD_DIR / "wheel"
    if wheel_dir.exists():
        shutil.rmtree(wheel_dir)
    run([python, "-m", "pip", "wheel", "--no-deps", "--disable-pip-version-check",
         "--wheel-dir", wheel_dir, ROOT])
    wheels = sorted(wheel_dir.glob("minecraft_server_creator-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected one wheel in {wheel_dir}, found {len(wheels)}")
    return wheels[0]


def install_app(python: Path, wheel: Path) -> None:
    run([python, "-m", "pip", "install", "--disable-pip-version-check",
         "--no-warn-script-location", "--no-cache-dir", wheel])
    # Smoke test: the package and its Qt bindings import in the bundled Python
    run([python, "-I", "-c",
         "import mcsc_gui, mcsc, PySide6.QtWidgets, tkinter; print('imports ok')"])


def clean_stage(python_dir: Path) -> None:
    """Remove what doesn't survive relocation or isn't needed at runtime."""
    # pip's .exe launchers (pip.exe, mcsc.exe, pyside6-*.exe) embed the absolute
    # path of the build machine's python.exe: they would be broken once
    # installed. The app starts with ``pythonw -m mcsc_gui`` and the updater
    # uses ``python -m pip``; pip recreates the launchers on the next update.
    scripts = python_dir / "Scripts"
    if scripts.exists():
        for launcher in scripts.glob("*.exe"):
            launcher.unlink()
    # Bytecode caches are rebuilt on demand; leaving them out keeps the
    # installer smaller and avoids stale caches pointing at the build paths.
    for cache in list(python_dir.rglob("__pycache__")):
        shutil.rmtree(cache, ignore_errors=True)
    # PySide6 wheels ship CMake build leftovers (objects-Debug/.../*.cpp.obj)
    # with very deep paths: useless at runtime, and they push the install
    # past Windows' 260-character path limit.
    qml = python_dir / "Lib" / "site-packages" / "PySide6" / "qml"
    for leftover in list(qml.rglob("objects-*")):
        if leftover.is_dir():
            shutil.rmtree(leftover, ignore_errors=True)


# Longest install folder we want to support: "C:\Users\<20 chars>\AppData\Local\
# Programs\Minecraft Server Creator\" is about 80 characters.
INSTALL_DIR_BUDGET = 90
MAX_PATH = 259


def check_path_lengths(stage: Path) -> None:
    """Fail if a file would exceed MAX_PATH once installed in a typical folder."""
    longest = max((f for f in stage.rglob("*") if f.is_file()),
                  key=lambda f: len(str(f.relative_to(stage))))
    relative = len(str(longest.relative_to(stage)))
    log(f"Longest bundled path: {relative} characters ({longest.relative_to(stage)})")
    if INSTALL_DIR_BUDGET + relative > MAX_PATH:
        raise SystemExit(f"{longest.relative_to(stage)} is too long for Windows' path "
                         "limit once installed: remove it in clean_stage()")


def find_iscc() -> Path | None:
    found = shutil.which("ISCC") or shutil.which("iscc")
    if found:
        return Path(found)
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6",
    ]
    for folder in candidates:
        if (folder / "ISCC.exe").exists():
            return folder / "ISCC.exe"
    return None


def compile_installer(version: str) -> Path:
    iscc = find_iscc()
    if iscc is None:
        raise SystemExit("Inno Setup 6 (ISCC.exe) not found: install it from "
                         "https://jrsoftware.org/isdl.php or pass --no-compile")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run([iscc, "/Q", f"/DAppVersion={version}", f"/DStageDir={STAGE_DIR}",
         f"/DOutputDir={OUTPUT_DIR}", ISS_FILE])
    installer = OUTPUT_DIR / f"mcsc-setup-{version}.exe"
    if not installer.exists():
        raise SystemExit(f"Inno Setup didn't produce {installer}")
    return installer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wheel", type=Path,
                        help="install this wheel instead of building the source tree")
    parser.add_argument("--no-compile", action="store_true",
                        help="prepare the bundled Python only, don't run Inno Setup")
    args = parser.parse_args()

    if sys.platform != "win32":
        raise SystemExit("The installer can only be built on Windows")

    version = project_version()
    log(f"Building the installer of version {version}")
    python_dir = extract_python(download_python())
    python = python_dir / "python.exe"
    wheel = args.wheel.resolve() if args.wheel else build_wheel(python)
    install_app(python, wheel)
    clean_stage(python_dir)
    check_path_lengths(STAGE_DIR)
    if args.no_compile:
        log(f"Files ready in {STAGE_DIR}")
        return
    installer = compile_installer(version)
    size = installer.stat().st_size / (1 << 20)
    log(f"Installer ready: {installer} ({size:.1f} MB)")


if __name__ == "__main__":
    main()
