#!/usr/bin/env python3
"""Diagnostic (read-only, static analysis, no DB needed): find every seeded algo_config
key that is never actually read by any real enforcement/business logic.

Why this exists (goal session 2026-09-13, "gaps in our approach" round 3): this bug class
kept getting found one key at a time by accident - min_market_cap_millions
(fixed 2026-09-13, commit 3b5109084), then max_short_interest_pct (fixed same day,
commit 74d261c32) were both seeded since early migrations, schema-validated, and even
exposed via trading_config.py's `get_stock_filter_config()` (a dict-builder that LOOKS
like real wiring but is itself dead code per .vulture_whitelist.py) - yet neither was ever
compared against a real value anywhere until fixed. There is no reason to believe those
were the only two; this script makes the search for the next one systematic instead of
one config key at a time being reported as a bug.

Method: every AlgoConfig.DEFAULTS key is defined as a dict-literal key in one of
algo/infrastructure/config/config_defaults_*.py. For each key, grep the whole repo for
its exact string literal, excluding files that only ever DEFINE or DISPLAY config
(default dicts, config_schema.py's validation ranges, dashboard/API response validators,
trading_config.py's dead dict-builder, tests, migrations, __pycache__). A key with zero
hits outside those files is read by nothing real - either genuinely dead/superseded
(document it, don't silently leave it looking live), or a real gap waiting to be wired in
(like the two above).

This is a STATIC, literal-string sweep - it will false-negative on any key built
dynamically (an f-string / .format() / string concatenation), so a "clean" result here is
not proof a key is enforced, only that no code enforces it via its literal name. Always
manually verify a candidate (read the surrounding code, check for a dynamic-construction
pattern like get_interval_sql()'s "{n}d" suffix mapping or a per-table key-name loop)
before treating it as confirmed dead or wiring it into new enforcement - see this script's
own false-positive history in MEMORY.md's audit_unenforced_config_20260913 note: an early
version of this excluded the entire algo/infrastructure/config/ directory and wrongly
flagged EconomicStressConfig-enforced keys as dead, because the real enforcement classes
(EconomicStressConfig, DataPatrolConfig, etc.) also live in that directory alongside the
pure-default-definition files.

Usage:
    python scripts/audit_unenforced_config.py
    python scripts/audit_unenforced_config.py --category "Liquidity Requirements"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that only ever DEFINE, VALIDATE, or DISPLAY config - never enforce it. A key
# appearing ONLY in these files is unenforced (a hit in any other real .py file means it's
# read by actual logic).
_EXCLUDE_FILES = {
    "algo/infrastructure/config/config_defaults_risk.py",
    "algo/infrastructure/config/config_defaults_market.py",
    "algo/infrastructure/config/config_defaults_signals.py",
    "algo/infrastructure/config/config_defaults_system.py",
    "algo/infrastructure/config/config_defaults_data_quality.py",
    "algo/infrastructure/config_schema.py",
    "dashboard/response_validators.py",
    "utils/validation/response_validators.py",
    "scripts/verify_safety_thresholds.py",
    ".vulture_whitelist.py",
}
# trading_config.py is a SPECIAL case: it looks like real wiring (dict-builder methods
# with names like get_stock_filter_config()) but every method in it is dead code per
# .vulture_whitelist.py - confirmed for min_market_cap_millions and max_short_interest_pct,
# both found ONLY there before being fixed. Track hits here separately so a key that
# appears ONLY in trading_config.py (beyond the defs/schema) is flagged as HIGH-PRIORITY
# (looks wired, isn't) rather than lumped in with genuinely-nowhere-referenced keys.
_DEAD_WIRING_FILE = "algo/infrastructure/config/trading_config.py"
_EXCLUDE_PREFIXES = ("tests/", "migrations/", ".git/")


def _discover_keys() -> dict[str, str]:
    """Return {config_key: source_file} for every key defined in a config_defaults_*.py."""
    keys: dict[str, str] = {}
    for f in sorted((REPO_ROOT / "algo/infrastructure/config").glob("config_defaults_*.py")):
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r'"([a-z0-9_]+)":\s*\(', text):
            keys.setdefault(m.group(1), str(f.relative_to(REPO_ROOT)).replace("\\", "/"))
    return keys


_EXCLUDED_DIR_PARTS = {"__pycache__", ".git", "worktrees", "node_modules", ".venv", ".mypy_cache", ".pytest_cache"}


def _all_py_files() -> list[Path]:
    """BUG FIX 2026-09-13 (found live while running this script during the goal session:
    it hung for minutes instead of finishing near-instantly on a pure-static grep). rglob
    walked into `.claude/worktrees/` - this repo runs well over 100 concurrent agent
    worktrees, each a full checkout - so every real source file was being re-scanned 100+
    times over, and any config key literal that happens to also appear in a worktree's own
    in-progress (possibly stale/reverted) copy of a file could produce a misleading
    "enforced" result that isn't true of the actual main-tree code being audited. Excluding
    `worktrees` (matches both `.claude/worktrees/*` and the sibling `algo-wt-*` checkouts
    some sessions use, none of which are nested under REPO_ROOT so this alone wouldn't
    catch those - they were never in scope for `rglob` to begin with since it only walks
    REPO_ROOT) makes this audit fast and restricted to the actual tree being reasoned about.
    """
    return [p for p in REPO_ROOT.rglob("*.py") if not any(part in _EXCLUDED_DIR_PARTS for part in p.parts)]


def _build_index(files: list[Path]) -> dict[str, str]:
    """Pre-read every file once (avoids re-scanning the whole repo per key - this repo has
    hundreds of config keys, and shelling out to `grep` per key proved unreliable on this
    Windows setup: subprocess.run(['grep', ...]) silently resolved to a different/broken
    grep than the interactive shell's, returning empty results for every query and
    producing a wall of false "orphaned" positives on keys later confirmed to have real
    usages. Pure-Python string search avoids depending on an external tool being on PATH
    at all, which is what a script meant to be re-run in this environment needs.
    """
    contents: dict[str, str] = {}
    for f in files:
        try:
            contents[str(f.relative_to(REPO_ROOT)).replace("\\", "/")] = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
    return contents


def _real_usages(key: str, index: dict[str, str]) -> tuple[list[str], bool]:
    """Return (files with a real usage, whether it appears in the dead-wiring file)."""
    needle = f'"{key}"'
    hits = [path for path, text in index.items() if needle in text]
    in_dead_wiring = _DEAD_WIRING_FILE in hits
    real = [
        f
        for f in hits
        if f not in _EXCLUDE_FILES and f != _DEAD_WIRING_FILE and not any(f.startswith(p) for p in _EXCLUDE_PREFIXES)
    ]
    return real, in_dead_wiring


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--category", help="Only check keys whose 4th tuple element matches this category")
    args = parser.parse_args()

    keys = _discover_keys()
    if args.category:
        keep = {}
        for f in set(keys.values()):
            text = (REPO_ROOT / f).read_text(encoding="utf-8")
            for m in re.finditer(r'"([a-z0-9_]+)":\s*\([^)]*"([^"]*)"\s*,?\s*\)', text, re.DOTALL):
                if m.group(1) in keys and m.group(2) == args.category:
                    keep[m.group(1)] = keys[m.group(1)]
        keys = keep

    high_priority: list[str] = []  # looks wired via trading_config.py's dead dict-builder, isn't
    orphaned: list[str] = []  # not referenced anywhere at all, not even fake-wiring

    index = _build_index(_all_py_files())
    for key in sorted(keys):
        real, in_dead_wiring = _real_usages(key, index)
        if real:
            continue
        if in_dead_wiring:
            high_priority.append(key)
        else:
            orphaned.append(key)

    print(f"Scanned {len(keys)} seeded algo_config keys.\n")
    print(f"HIGH-PRIORITY ({len(high_priority)}) - only referenced via trading_config.py's dead dict-builder,")
    print("looks wired to a casual reader but is not read by any real code:")
    for k in high_priority:
        print(f"  {k}")
    print(f"\nORPHANED ({len(orphaned)}) - not referenced by any real code, not even fake-wiring")
    print("(may be genuinely superseded/dead - verify before assuming it's a gap, see docstring):")
    for k in orphaned:
        print(f"  {k}")

    if high_priority or orphaned:
        sys.exit(1)


if __name__ == "__main__":
    main()
