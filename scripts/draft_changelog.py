"""
Draft the release notes of the next version from the git history.

Run it in the release PR (``develop -> main``)::

    python scripts/draft_changelog.py              # commits since the last tag
    python scripts/draft_changelog.py --dry-run    # print the entry, don't write
    python scripts/draft_changelog.py --version 3.1.0 --include-fixes
    python scripts/draft_changelog.py --since v3.0.0 --force

It reads the conventional commits (``feat(scope): subject (#12)``) since the
last tag, proposes the next version (major for breaking changes, minor if
there's a ``feat``, patch otherwise) and adds a draft entry at the top of
``src/mcsc_gui/static/changelog.json``. The draft is a starting point: rewrite
it in user-facing language, remove internal changes and add the translations.

Standard library + git only: this script is not part of the app.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_PATH = ROOT / "src" / "mcsc_gui" / "static" / "changelog.json"
PYPROJECT_PATH = ROOT / "pyproject.toml"

_COMMIT_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<subject>.+?)"
    r"(?:\s+\(#(?P<pr>\d+)\))?\s*$"
)
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
_SEPARATOR = "\x1e"  # between commits in the git log output
_FIELD = "\x1f"      # between subject and body


@dataclass(frozen=True)
class Commit:
    """A conventional commit."""

    type: str
    scope: str | None
    breaking: bool
    subject: str
    pr: int | None = None


def parse_commit(subject: str, body: str = "") -> Commit | None:
    """A :class:`Commit` from a commit message; None if it's not a conventional commit."""
    match = _COMMIT_RE.match(subject.strip())
    if match is None:
        return None
    breaking = bool(match["bang"]) or bool(re.search(r"^BREAKING[ -]CHANGE:", body, re.M))
    return Commit(
        type=match["type"].lower(),
        scope=match["scope"] or None,
        breaking=breaking,
        subject=match["subject"].strip(),
        pr=int(match["pr"]) if match["pr"] else None,
    )


def parse_version(value: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.match(value.strip())
    return tuple(int(x) for x in match.groups()) if match else None  # type: ignore[return-value]


def next_version(current: str, commits: list[Commit]) -> str:
    """Major for breaking changes, minor if there's a feature, patch otherwise."""
    parsed = parse_version(current)
    if parsed is None:
        raise ValueError(f"Invalid current version: {current!r}")
    major, minor, patch = parsed
    if any(c.breaking for c in commits):
        return f"{major + 1}.0.0"
    if any(c.type == "feat" for c in commits):
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _sentence(text: str) -> str:
    text = text.strip().rstrip(".")
    return text[:1].upper() + text[1:]


def draft_entry(version: str, commits: list[Commit], *, include_fixes: bool = False,
                today: date | None = None) -> dict | None:
    """A changelog entry with the commits as English highlights; None if there's nothing."""
    wanted = [c for c in commits if c.type == "feat" or c.breaking]
    if include_fixes:
        wanted += [c for c in commits if c.type == "fix" and not c.breaking]
    highlights: list[str] = []
    for commit in wanted:
        text = _sentence(commit.subject)
        if text and text.lower() not in (h.lower() for h in highlights):
            highlights.append(text)
    if not highlights:
        return None
    return {
        "version": version,
        "date": (today or date.today()).isoformat(),
        "highlights": {"en": highlights},
    }


def insert_entry(changelog: dict, entry: dict, *, force: bool = False) -> dict:
    """``changelog`` with ``entry`` added (or replaced, with ``force``), newest first."""
    releases = [r for r in changelog.get("releases", []) if isinstance(r, dict)]
    existing = [r for r in releases if r.get("version") == entry["version"]]
    if existing and not force:
        raise ValueError(f"The changelog already has version {entry['version']} "
                         "(use --force to replace it)")
    releases = [r for r in releases if r.get("version") != entry["version"]]
    releases.append(entry)
    releases.sort(key=lambda r: parse_version(str(r.get("version", ""))) or (0, 0, 0),
                  reverse=True)
    return {"schema": changelog.get("schema", 1), "releases": releases}


# ------------------------------------------------------------------ git / io

def _git(*args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", check=True)
    except FileNotFoundError as e:
        raise RuntimeError("git is not installed") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(e.stderr.strip() or f"git {' '.join(args)} failed") from e
    return result.stdout


def latest_tag(tags: list[str]) -> str | None:
    """The tag with the highest version (``v3.0.1`` > ``v3.0.0`` > ``1.2.4``), or None."""
    versioned = [(parse_version(t), t) for t in tags if parse_version(t) is not None]
    return max(versioned)[1] if versioned else None


def last_tag() -> str | None:
    """The latest release tag, or None.

    Not ``git describe``: with Git Flow the tags are on ``main``, so from
    ``develop`` the last one isn't reachable. ``<tag>..HEAD`` still excludes
    everything already released, because ``main`` contains those commits.
    """
    try:
        return latest_tag(_git("tag", "--list").split())
    except RuntimeError:
        return None


def read_commits(since: str | None) -> list[Commit]:
    """The conventional commits after ``since`` (all of them if None), oldest first."""
    revision = f"{since}..HEAD" if since else "HEAD"
    output = _git("log", revision, "--no-merges", "--reverse",
                  f"--pretty=%s{_FIELD}%b{_SEPARATOR}")
    commits = []
    for raw in output.split(_SEPARATOR):
        if not raw.strip():
            continue
        subject, _sep, body = raw.strip("\n").partition(_FIELD)
        commit = parse_commit(subject, body)
        if commit is not None:
            commits.append(commit)
    return commits


def current_version() -> str:
    with PYPROJECT_PATH.open("rb") as file:
        return tomllib.load(file)["project"]["version"]


def load_file(path: Path) -> dict:
    if not path.exists():
        return {"schema": 1, "releases": []}
    return json.loads(path.read_text(encoding="utf-8"))


def dump(changelog: dict) -> str:
    return json.dumps(changelog, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--since", help="tag or commit to start from (default: the last tag)")
    parser.add_argument("--version", help="version of the entry (default: computed from commits)")
    parser.add_argument("--include-fixes", action="store_true", help="also list the fixes")
    parser.add_argument("--dry-run", action="store_true", help="print the entry, don't write")
    parser.add_argument("--force", action="store_true", help="replace an existing entry")
    parser.add_argument("--file", type=Path, default=CHANGELOG_PATH, help="changelog to update")
    args = parser.parse_args(argv)

    try:
        since = args.since or last_tag()
        if since is None and not args.version:
            print("No tag found: pass --since or --version", file=sys.stderr)
            return 1
        commits = read_commits(since)
        version = args.version or next_version(current_version(), commits)
        if parse_version(version) is None:
            print(f"Invalid version: {version!r}", file=sys.stderr)
            return 1
        version = ".".join(str(n) for n in parse_version(version))
        entry = draft_entry(version, commits, include_fixes=args.include_fixes)
        if entry is None:
            hint = "" if args.include_fixes else " (try --include-fixes)"
            print(f"Nothing to add for {version} since {since or 'the start'}{hint}.")
            return 0
        if args.dry_run:
            print(dump(entry), end="")
            return 0
        changelog = insert_entry(load_file(args.file), entry, force=args.force)
        args.file.write_text(dump(changelog), encoding="utf-8")
    except (RuntimeError, ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Added a draft for {version} ({len(entry['highlights']['en'])} highlights, "
          f"since {since or 'the start'}) to {args.file}")
    print("Now rewrite it in user-facing language, remove internal changes "
          "and add the 'it' translation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
