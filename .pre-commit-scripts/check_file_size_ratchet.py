#!/usr/bin/env python
"""File-size ratchet: blocks already-oversized Python files from growing further,
and caps brand-new files at a smaller hard limit.

Does not try to fix existing bloat (30+ files already run 1,500-6,000 lines) -
that's a real refactor project, not a pre-commit job. It only stops the debt
from getting worse and stops new files from joining that list. Baseline lives
in .file-size-baseline.json and auto-tightens whenever a file shrinks.

Baselines are read from git HEAD (the last commit), never from the working
tree - a bump to a file's cap and the growth it excuses cannot land in the
same commit. See load_baseline()'s comment for why that matters.

HARD_CEILING exists because the per-.py-file check above was never the whole
story: a commit that edits ONLY .file-size-baseline.json touches no .py file,
so it never appeared in `entries` at all and sailed through with zero
validation - the documented "raise the cap in a separate prior commit"
escape hatch had no upper bound. That's exactly how this went wrong in
practice: files kept getting a fresh baseline bump every time a feature
needed a few more lines, so "frozen at whatever size it happened to be" kept
sliding upward instead of ever forcing a split (see CLAUDE.md's
bloater-decomposition note and MEMORY.md - a 2026-09-05 decision to split one
bloater per session went unenforced and several of the named worst offenders
grew by hundreds of lines afterward instead of shrinking). Past HARD_CEILING,
raising a file's baseline is refused outright, in any commit, no override -
the only way to add code to a file already this large is to extract a module
first and shrink it back under the ceiling.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

BASELINE_PATH = Path(".file-size-baseline.json")
NEW_FILE_CAP = 800
HARD_CEILING = 2000

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
    # Read the last COMMITTED baseline (git HEAD), not the working-tree file. pre-commit
    # runs hooks against the staged snapshot, so reading straight off disk here would let a
    # single commit both raise a file's cap (by editing the number in .file-size-baseline.json)
    # and grow the file to match it - the check would compare the file against its own
    # just-inflated limit and always pass. That hole was real: loaders/load_value_quality_
    # growth_metrics.py grew 3263 -> 6070 lines across ~15 commits this way, each one bumping
    # the baseline just far enough to cover that commit's own growth. Reading from HEAD instead
    # means a legitimate cap raise must land in its own prior commit with no code change riding
    # along - visible in git log, not smuggled inside an unrelated fix.
    result = subprocess.run(
        ["git", "show", f"HEAD:{BASELINE_PATH.as_posix()}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return json.loads(result.stdout)
    # No committed baseline yet (e.g. this is the commit that first adds it).
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


def load_baseline_at(ref: str) -> dict:
    result = subprocess.run(["git", "show", f"{ref}:{BASELINE_PATH.as_posix()}"], capture_output=True, text=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    return {}


def file_lines_at(ref: str, rel: str) -> int | None:
    """Line count of rel as it existed at ref, or None if it doesn't exist there (deleted)."""
    result = subprocess.run(["git", "show", f"{ref}:{rel}"], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return len(result.stdout.splitlines())


def check_diff(entries: list[tuple[str, str | None]], baseline: dict, current_lines: dict) -> tuple[list[str], dict]:
    """Shared ratchet logic. current_lines maps rel -> line count (or None if deleted).
    Returns (failures, updated_baseline)."""
    failures = []
    updated = dict(baseline)
    for rel, old_rel in entries:
        current = current_lines.get(rel)
        if current is None:
            continue
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
            if prior >= HARD_CEILING:
                failures.append(
                    f"  GROWN  {rel}: {current} lines (was {prior}, already past the "
                    f"{HARD_CEILING}-line hard ceiling). No baseline raise will be accepted "
                    f"for this file - extract a module and shrink it back down first."
                )
            else:
                failures.append(
                    f"  GROWN  {rel}: {current} lines (was {prior}). Already-oversized legacy "
                    f"debt - growth is blocked, extract a module instead. If this growth is "
                    f"truly deliberate (e.g. a generated file or data table), raise the value "
                    f"for this path in .file-size-baseline.json with a one-line reason in a "
                    f"SEPARATE prior commit that touches no other code - baselines are read "
                    f"from git HEAD, so a same-commit bump no longer bypasses this check. That "
                    f"raise itself is checked against the {HARD_CEILING}-line hard ceiling."
                )
        elif current < prior:
            updated[rel] = current
    return failures, updated


def check_baseline_raise(old: dict, new: dict) -> list[str]:
    """Validates the baseline file's OWN diff, independent of whether any .py file also
    changed in the same commit. Without this, a commit that edits only
    .file-size-baseline.json - exactly what every "raise the baseline" commit does - never
    appears in check_diff()'s .py-only `entries` list and was never checked at all."""
    failures = []
    for rel, new_val in new.items():
        old_val = old.get(rel)
        if old_val is None or new_val <= old_val:
            continue
        if new_val > HARD_CEILING:
            failures.append(
                f"  BASELINE-RAISE  {rel}: {old_val} -> {new_val} exceeds the "
                f"{HARD_CEILING}-line hard ceiling. Split the file before raising its cap "
                f"further - no override."
            )
    return failures


def main_local() -> int:
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
    staged_paths = {rel for rel, _ in parse_staged(staged)}

    entries = [(rel, old) for rel, old in parse_staged(staged) if rel.endswith(".py") and not is_excluded(rel)]

    baseline = load_baseline()
    failures: list[str] = []
    updated = dict(baseline)

    if entries:
        current_lines = {rel: count_lines(Path(rel)) for rel, _ in entries if Path(rel).exists()}
        diff_failures, updated = check_diff(entries, baseline, current_lines)
        failures.extend(diff_failures)

    # Checked unconditionally, independent of `entries` - a commit that edits only the
    # baseline file (no .py changes) must still be validated. See check_baseline_raise().
    if str(BASELINE_PATH.as_posix()) in staged_paths:
        staged_baseline = json.loads(
            subprocess.run(
                ["git", "show", f":{BASELINE_PATH.as_posix()}"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
        failures.extend(check_baseline_raise(baseline, staged_baseline))

    if updated != baseline:
        BASELINE_PATH.write_text(json.dumps(dict(sorted(updated.items())), indent=2) + "\n", encoding="utf-8")
        # RETRY 2026-09-07 (goal session: heavy concurrent-session churn made this repo's
        # .git/index.lock transiently held often enough that a bare `git add` here crashed
        # the whole hook - not a real file-size violation, just lock contention from another
        # session's git process. Same "verify/wait, don't force" discipline as this session's
        # manual git-lock handling: a few retries with backoff, no --force, no skipping the add.
        last_error: subprocess.CalledProcessError | None = None
        for attempt in range(15):
            try:
                subprocess.run(["git", "add", str(BASELINE_PATH)], check=True)
                last_error = None
                break
            except subprocess.CalledProcessError as exc:
                last_error = exc
                time.sleep(4)
        if last_error is not None:
            raise last_error

    if not entries and not failures:
        return 0

    if failures:
        print("File-size ratchet failed:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    return 0


def main_ci_range(base_sha: str, head_sha: str) -> int:
    # CI has nothing staged (a plain checkout's index matches HEAD), so `git diff --cached`
    # used by main_local() always sees zero entries and silently no-ops here - this codepath
    # exists so CI actually enforces the ratchet instead of rubber-stamping every push/PR that
    # skips (or never installs) the local pre-commit hook. Replays the range commit-by-commit,
    # each one diffed against its own parent and checked against the baseline AS OF that parent
    # - matching exactly what would have happened had pre-commit run on every individual local
    # commit, so a two-commit "bump the baseline, then grow the file to match" trick within one
    # PR is still caught (each commit is judged against the baseline that existed before it).
    commits = subprocess.run(
        ["git", "rev-list", "--reverse", f"{base_sha}..{head_sha}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    all_failures = []
    for commit in commits:
        parent = f"{commit}^"
        diff_lines = subprocess.run(
            ["git", "diff", "--name-status", "--diff-filter=ACMR", "-M", parent, commit],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        changed_paths = {rel for rel, _ in parse_staged(diff_lines)}
        entries = [(rel, old) for rel, old in parse_staged(diff_lines) if rel.endswith(".py") and not is_excluded(rel)]

        commit_failures: list[str] = []
        if entries:
            baseline = load_baseline_at(parent)
            current_lines = {rel: file_lines_at(commit, rel) for rel, _ in entries}
            diff_failures, _ = check_diff(entries, baseline, current_lines)
            commit_failures.extend(diff_failures)

        # Same unconditional check as main_local() - a baseline-only commit (no .py files
        # in `entries`) must still be validated against the hard ceiling.
        if str(BASELINE_PATH.as_posix()) in changed_paths:
            old_baseline = load_baseline_at(parent)
            new_baseline = load_baseline_at(commit)
            commit_failures.extend(check_baseline_raise(old_baseline, new_baseline))

        all_failures.extend(f"{f}  [commit {commit[:8]}]" for f in commit_failures)

    if all_failures:
        print("File-size ratchet failed:\n" + "\n".join(all_failures), file=sys.stderr)
        return 1
    return 0


def main() -> int:
    if len(sys.argv) == 3:
        # Invoked as: check_file_size_ratchet.py <base_sha> <head_sha>  (CI mode)
        return main_ci_range(sys.argv[1], sys.argv[2])
    return main_local()


if __name__ == "__main__":
    sys.exit(main())
