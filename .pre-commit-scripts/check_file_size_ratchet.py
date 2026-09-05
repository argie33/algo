#!/usr/bin/env python
"""File-size ratchet: blocks already-oversized Python files from growing further,
and caps brand-new files at a smaller hard limit.

Does not try to fix existing bloat (30+ files already run 1,500-4,400 lines) -
that's a real refactor project, not a pre-commit job. It only stops the debt
from getting worse and stops new files from joining that list. Baseline lives
in .file-size-baseline.json and auto-tightens whenever a file shrinks.
"""

import json
import subprocess
import sys
from pathlib import Path

BASELINE_PATH = Path(".file-size-baseline.json")
NEW_FILE_CAP = 800

EXCLUDE_PREFIXES = (
    "tests/",
    ".claude/worktrees/",
    "migrations/",
)


def count_lines(path: Path) -> int:
    with open(path, encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f)


def is_excluded(path_str: str) -> bool:
    if "node_modules/" in path_str:
        return True
    return any(path_str.startswith(p) for p in EXCLUDE_PREFIXES)


def load_baseline() -> dict:
    if BASELINE_PATH.exists():
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {}


def parse_staged(lines: list[str]) -> list[tuple[str, str | None]]:
    """Returns (path, renamed_from) pairs. renamed_from is None for plain adds/modifies."""
    entries = []
    for line in lines:
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R"):
            entries.append((parts[2], parts[1]))
        else:
            entries.append((parts[1], None))
    return entries


def main() -> int:
    # --diff-filter=ACMR + -M: renames must be included, not just add/modify - otherwise
    # renaming a bloated file while growing it past its cap (or past 800 for a "new" path)
    # completely bypasses this check whenever git's similarity heuristic still calls it a
    # rename instead of a delete+add (the default threshold is 50% similarity).
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-status", "--diff-filter=ACMR", "-M"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    entries = [(rel, old) for rel, old in parse_staged(staged) if rel.endswith(".py") and not is_excluded(rel)]
    if not entries:
        return 0

    baseline = load_baseline()
    failures = []
    updated = dict(baseline)

    for rel, old_rel in entries:
        path = Path(rel)
        if not path.exists():
            continue
        current = count_lines(path)
        prior = baseline.get(rel)
        if prior is None and old_rel is not None:
            prior = baseline.get(old_rel)
            updated.pop(old_rel, None)

        if prior is None:
            if current > NEW_FILE_CAP:
                failures.append(
                    f"  NEW    {rel}: {current} lines (new-file cap is {NEW_FILE_CAP}). "
                    f"Split this up before it becomes the next entry in CLAUDE.md's "
                    f"bloater list."
                )
            else:
                updated[rel] = current
        elif current > prior:
            failures.append(
                f"  GROWN  {rel}: {current} lines (was {prior}). Already-oversized legacy "
                f"debt - growth is blocked, extract a module instead. If this growth is "
                f"deliberate (e.g. a generated file or data table), bump the value for "
                f"this path in .file-size-baseline.json in the same commit with a "
                f"one-line reason."
            )
        elif current < prior:
            updated[rel] = current

    if updated != baseline:
        BASELINE_PATH.write_text(json.dumps(dict(sorted(updated.items())), indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", str(BASELINE_PATH)], check=True)

    if failures:
        print("File-size ratchet failed:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
