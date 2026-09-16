#!/usr/bin/env python3
"""Report the state of every git worktree under .claude/worktrees/ so abandoned agent work
gets caught before it silently rots (goal: 2026-09-16, "agent seems to spin one up and then
it gets abandoned... we doing work and not reaping the benefits" - a from-scratch audit that
day found 20 worktrees, several with real never-committed trading-execution/scoring code
sitting unreaped for days). Not wired into any scheduled task - run by hand (or ask an agent
to run it) periodically, e.g. as part of the existing monthly-cleanup pass in CLAUDE.md.

Usage:
  python scripts/check_worktree_health.py
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd or REPO_ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def main() -> int:
    listing = _run(["worktree", "list", "--porcelain"])
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in listing.splitlines():
        if line.startswith("worktree "):
            if current:
                entries.append(current)
            current = {"path": line.split(" ", 1)[1]}
        elif line.startswith("branch "):
            current["branch"] = line.split(" ", 1)[1].replace("refs/heads/", "")
    if current:
        entries.append(current)

    main_path = str(REPO_ROOT).replace("\\", "/")
    flagged = []
    for entry in entries:
        path = entry["path"].replace("\\", "/")
        if path == main_path:
            continue
        branch = entry.get("branch", "(detached)")
        status = _run(["status", "--short"], cwd=Path(entry["path"]))
        ahead = _run(["rev-list", "--count", f"main..{branch}"]) if branch != "(detached)" else "?"
        behind = _run(["rev-list", "--count", f"{branch}..main"]) if branch != "(detached)" else "?"
        uncommitted_lines = len(status.splitlines()) if status else 0

        print(f"\n{entry['path']}")
        print(f"  branch: {branch}  ahead={ahead}  behind={behind}  uncommitted_files={uncommitted_lines}")

        risk = uncommitted_lines > 0 or (ahead.isdigit() and int(ahead) > 0)
        if risk:
            flagged.append(entry["path"])
        if uncommitted_lines:
            print("  UNCOMMITTED CHANGES - do not delete without reviewing:")
            for line in status.splitlines()[:10]:
                print(f"    {line}")

    print(
        f"\n{len(entries) - 1} worktree(s) checked, {len(flagged)} have unreaped work "
        "(uncommitted changes and/or commits not yet in main)."
    )
    if flagged:
        print("Review each before deleting - see CLAUDE.md's worktree-hygiene note.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
