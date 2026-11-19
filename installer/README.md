# Windows installer

`mcsc-setup-<version>.exe` installs Minecraft Server Creator for users who don't
have Python. It doesn't touch any system Python: it ships its own.

## How it works

- **Private Python**: a relocatable CPython 3.12 build from
  [python-build-standalone](https://github.com/astral-sh/python-build-standalone),
  pinned with its SHA-256 in `build_installer.py`. Unlike the "embeddable" Python
  from python.org, it includes pip and tkinter, which the in-app updater needs.
- **Prebuilt**: MCSC and its dependencies are installed into that Python at build
  time. The installer just copies files: no internet needed while installing.
- **Per-user install** in `%LOCALAPPDATA%\Programs\Minecraft Server Creator`, with
  no admin rights. The folder stays writable, so the in-app updater
  (`python -m pip install --upgrade`) keeps working.
- **Shortcuts**: Start menu (always) and desktop (optional). Both run
  `python\pythonw.exe -m mcsc_gui` with the same AppUserModelID as the app.
- **Upgrade**: running a newer installer replaces the `python` folder from
  scratch and closes a running MCSC first.
- **Uninstall** (Settings > Apps, or `unins000.exe`): removes the program folder
  and its shortcuts. Servers, settings and logs in `%LOCALAPPDATA%\mcsc` are kept.

## Building locally

Requires Windows, Python 3.11+ (only to run the script) and
[Inno Setup 6](https://jrsoftware.org/isdl.php)
(`winget install JRSoftware.InnoSetup`).

```bash
python installer/build_installer.py
```

Output: `dist/installer/mcsc-setup-<version>.exe` (unsigned). The version comes
from `pyproject.toml`. `--wheel <file>` installs a given wheel instead of building
this source tree. `--no-compile` only prepares `build/installer/stage`.

To bump the bundled Python, change `PYTHON_RELEASE`, `PYTHON_ASSET` and
`PYTHON_SHA256` in `build_installer.py`.

## Release and signing (GitHub Actions + SignPath)

`.github/workflows/installer.yml` runs when a GitHub release is published. It
builds the installer, sends it to SignPath with the `release-signing` policy,
waits for the approval (up to one hour), checks the signature and attaches the
signed `.exe` to the release. A manual run (*Actions > Windows installer > Run
workflow*) uses the `test-signing` policy and keeps the result as a workflow
artifact.

The release tag must match the version in `pyproject.toml` (`v3.0.0` or `3.0.0`).

### One-time SignPath setup

1. Get a SignPath organization: the free
   [SignPath Foundation](https://signpath.org/) program for open source projects
   (see the license note below), or a paid plan on [signpath.io](https://signpath.io/).
2. In SignPath, install the GitHub trusted build system for the repository and
   create a project (for example with slug `minecraft-server-creator`).
3. In that project, set the default artifact configuration to the contents of
   `installer/signpath-artifact-configuration.xml`. SignPath validates it when you
   save it.
4. Create the signing policies `test-signing` and `release-signing`. They are the
   slugs the workflow uses.
5. Create an API token for a CI user with the *Submitter* role on both policies.
6. In GitHub, go to *Settings > Secrets and variables > Actions* and add:
   - secret `SIGNPATH_API_TOKEN`: the API token;
   - variable `SIGNPATH_ORGANIZATION_ID`: the organization id;
   - variable `SIGNPATH_PROJECT_SLUG`: the project slug.

### SignPath Foundation requirements

- **License**: the project must use an OSI-approved open source license.
  MCSC is currently under CC BY-NC-SA 4.0, which is not OSI-approved. To use the
  free program, the license has to change (for example to GPL-3.0 or MIT).
  Otherwise, use a paid SignPath plan.
- The project page must have a **"Code signing policy"** section (see the main
  README) with the sentence "Free code signing provided by SignPath.io,
  certificate by SignPath Foundation", the team roles, and a privacy policy.
- Every team member needs MFA on GitHub and SignPath. Every release signing
  request must be approved by an approver.

Only the setup `.exe` is signed. The files it installs (python.exe, Qt DLLs) keep
their original signature, or have none.
