#!/usr/bin/env python3
"""Inventory every data-integrity detector we have and flag ones that are not actually
live - the "gap in our approach" class of bug (see memory:
price_daily_retroactive_corruption_never_cleaned_up_20260913 /
worktree_backlog_35_unmerged_branches_measurable_gap_20260912): a detection script gets
built, verified once, and then never runs again because it was never wired into anything
recurring, or it landed on a worktree branch that never got merged to main.

This script answers three separate questions, each checkable in code instead of by memory:

1. DataPatrol checkers - is every checker class actually instantiated in
   DataPatrol.run()'s hardcoded list (algo/monitoring/data_patrol/base.py), so it runs on
   every scheduled patrol pass? A checker class that exists in checks/__init__.py's
   __all__ but is missing from that list is defined but silently never executed.
2. XBRL "second opinion" layers - is each layer's run() actually called from
   scripts/xbrl_second_opinion_daily.py (the thing the Windows Scheduled Task invokes)?
   Cross-checked against whether that task is actually registered and Ready right now
   (not just "written" - see the load-bearing distinction in CLAUDE.md).
3. Every other scripts/*.py "check_*"/"audit_*"/"monitor_*" file - is it referenced from
   anywhere else in the repo (a scheduled entrypoint, another script, a test)? Zero
   references doesn't prove it's abandoned (some are deliberately manual/periodic tools -
   see CLAUDE.md's documented `--dry-run` usage examples), but it's the same shape of
   signal that would have caught check_price_daily_isolated_spikes.py sitting unused.

Usage:
  python scripts/data_integrity_coverage_audit.py
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKS_DIR = REPO_ROOT / "algo" / "monitoring" / "data_patrol" / "checks"
SCRIPTS_DIR = REPO_ROOT / "scripts"
BASE_PY = REPO_ROOT / "algo" / "monitoring" / "data_patrol" / "base.py"
SECOND_OPINION_DAILY = SCRIPTS_DIR / "xbrl_second_opinion_daily.py"

# Layers whose run() is expected to be called from xbrl_second_opinion_daily.py.
EXPECTED_SECOND_OPINION_LAYERS = [
    "xbrl_yfinance_crosscheck",
    "xbrl_calculation_linkbase_check",
    "xbrl_dqc_arelle_check",
]

# scripts/*.py that are deliberately manual/periodic tools per CLAUDE.md, not meant to be
# wired into any always-on schedule - excluded from the "orphan candidate" flag so the
# report isn't dominated by known-fine cases.
DOCUMENTED_MANUAL_TOOLS = {
    "xbrl_concept_coverage_scan.py",
    "xbrl_yfinance_crosscheck.py",
    "xbrl_calculation_linkbase_check.py",
    "xbrl_dqc_arelle_check.py",
    "xbrl_segment_sum_reconciliation.py",
    "xbrl_second_opinion_daily.py",
    "monitor_data_staleness.py",
    "verify_eventbridge_scheduler.py",
    "run_local_orchestrator.py",
    "local_loader_scheduler.py",
    "xbrl_frames_check.py",
    "xbrl_dera_bulk_scan.py",
    "xbrl_dera_bulk_gap_filler.py",
    "triage_xbrl_continuity_gaps.py",
    "xbrl_scored_headline_count.py",
    "xbrl_concept_continuity_scan.py",
}


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, check=False)
    return result.stdout.strip()


def audit_data_patrol_checkers() -> list[str]:
    """Every class exported from checks/__init__.py must appear in base.py's checkers list."""
    problems = []
    init_src = (CHECKS_DIR / "__init__.py").read_text()
    exported = set(re.findall(r'"(\w+Checker)"', init_src))

    base_src = BASE_PY.read_text()
    match = re.search(r"checkers:\s*list\[BaseCheck\]\s*=\s*\[(.*?)\]", base_src, re.DOTALL)
    wired = set(re.findall(r"(\w+Checker)\(", match.group(1))) if match else set()

    print(f"DataPatrol: {len(exported)} checker(s) exported, {len(wired)} actually wired into run()")
    missing = exported - wired
    if missing:
        problems.append(f"DataPatrol checkers exported but NEVER instantiated in run(): {sorted(missing)}")
        print(f"  GAP: {sorted(missing)} - defined but silently never executed")
    else:
        print("  OK: every exported checker is wired")
    return problems


def audit_second_opinion_layers() -> list[str]:
    problems = []
    if not SECOND_OPINION_DAILY.exists():
        problems.append("scripts/xbrl_second_opinion_daily.py does not exist on main")
        return problems

    daily_src = SECOND_OPINION_DAILY.read_text()
    print("\nXBRL second-opinion layers:")
    for layer in EXPECTED_SECOND_OPINION_LAYERS:
        wired = layer in daily_src
        script_exists = (SCRIPTS_DIR / f"{layer}.py").exists()
        status = "OK" if (wired and script_exists) else "GAP"
        print(f"  [{status}] {layer}: script_on_main={script_exists} wired_into_daily={wired}")
        if status == "GAP":
            problems.append(f"{layer}: script_on_main={script_exists} wired_into_daily={wired}")

    tasks = _scheduled_task_states()
    for task in ("xbrl-second-opinion", "xbrl-segment-sum-monthly"):
        state = tasks.get(task)
        status = "OK" if state == "Ready" else "GAP"
        print(f"  [{status}] Windows Scheduled Task '{task}': state={state!r}")
        if status == "GAP":
            problems.append(f"scheduled task '{task}' not Ready (state={state!r})")
    return problems


def _scheduled_task_states() -> dict[str, str]:
    """Best-effort: only meaningful on the Windows machine these tasks are registered on."""
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                'Get-ScheduledTask -TaskPath "\\algo\\" -ErrorAction SilentlyContinue '
                '| ForEach-Object { "$($_.TaskName)|$($_.State)" }',
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        states = {}
        for line in result.stdout.strip().splitlines():
            if "|" in line:
                name, state = line.split("|", 1)
                states[name.strip()] = state.strip()
        return states
    except (OSError, subprocess.SubprocessError):
        return {}


def audit_orphan_scripts() -> list[str]:
    """A script referenced nowhere else in the repo is a candidate for the same gap as
    check_price_daily_isolated_spikes.py: built, works, invoked by no automated path.
    """
    problems = []
    print("\nStandalone check/audit/monitor scripts - reference count elsewhere in repo:")
    candidates = sorted(
        p.name
        for p in SCRIPTS_DIR.glob("*.py")
        if re.match(r"^(check|audit|monitor|verify)_", p.name) and p.name not in DOCUMENTED_MANUAL_TOOLS
    )
    for name in candidates:
        stem = name[:-3]
        hits = _git("grep", "-l", stem, "--", "*.py", "*.ps1", "*.tf", "*.yml", "*.yaml")
        referencing_files = [f for f in hits.splitlines() if f != f"scripts/{name}"]
        status = "OK" if referencing_files else "ORPHAN?"
        print(f"  [{status}] {name}: referenced in {len(referencing_files)} other file(s)")
        if not referencing_files:
            problems.append(f"{name}: zero references outside itself - verify it's still invoked somewhere")
    return problems


def audit_unmerged_worktree_branches() -> list[str]:
    """The generalized version of the price_daily gap: a completed fix sitting on a
    branch that never got merged to main is invisible to every check above."""
    problems = []
    print("\nWorktree branches with unmerged content vs main:")
    branches_raw = _git("worktree", "list", "--porcelain")
    branches = [
        line.split(" ", 1)[1].replace("refs/heads/", "")
        for line in branches_raw.splitlines()
        if line.startswith("branch ")
    ]
    unmerged = []
    for b in branches:
        if b == "main":
            continue
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", b, "main"],
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            unmerged.append(b)
    print(f"  {len(unmerged)}/{len(branches) - 1} branches not ancestors of main")
    if unmerged:
        problems.append(f"{len(unmerged)} unmerged branch(es) - review for stranded finished work: {unmerged}")
    return problems


def main() -> int:
    all_problems: list[str] = []
    all_problems += audit_data_patrol_checkers()
    all_problems += audit_second_opinion_layers()
    all_problems += audit_orphan_scripts()
    all_problems += audit_unmerged_worktree_branches()

    print(
        f"\n{'=' * 70}\n{len(all_problems)} coverage gap(s) found"
        if all_problems
        else f"\n{'=' * 70}\nNo coverage gaps found"
    )
    for p in all_problems:
        print(f"  - {p}")
    return 1 if all_problems else 0


if __name__ == "__main__":
    sys.exit(main())
