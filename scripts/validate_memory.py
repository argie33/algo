#!/usr/bin/env python3
"""
Memory validation script - enforces safety standards before memory is accepted.
Runs before any memory write to catch violations.
"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Fix encoding on Windows (but not during pytest)
if sys.stdout.encoding and "utf" not in sys.stdout.encoding.lower() and "pytest" not in sys.modules:
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MEMORY_DIR = Path.home() / ".claude" / "projects" / "C--Users-arger-code-algo" / "memory"

# Red flag patterns that indicate unverified claims
RED_FLAGS = {
    "bulletproof": "Absolute claim without verification",
    "production.?ready": "Claim ready for prod without test method",
    "verified.?working": "Verified but no test method shown",
    "all.?tests.?pass": "Status claim that rots quickly",
    "safe.?for.?real.?money": "High-stakes claim needs rigorous proof",
    "working.?end.?to.?end": "E2E claim without reproduction steps",
    "works.?perfectly": "Absolute claim - always false eventually",
    "no.?known.?bugs": "Impossible claim - always more bugs",
    "100%.+success": "Absolute percentages are red flags",
}

# Required fields for memory files
REQUIRED_FIELDS = {
    "feedback": ["name", "description", "type", "Why:", "How to apply:"],
    "project": ["name", "description", "type", "Why:", "How to apply:"],
    "reference": ["name", "description", "type"],
    "user": ["name", "description", "type"],
}

# Red flag: tested status without test method
TESTED_WITHOUT_METHOD = r"(?i)(tested|verified|confirmed):.*?(?<!method:|command:|how:)"


def check_red_flags(content: str, filename: str) -> list[str]:
    """Check for unverified claims."""
    issues = []
    for pattern, reason in RED_FLAGS.items():
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            line_num = content[: match.start()].count("\n") + 1
            issues.append(
                f"  [FAIL] Line {line_num} [{filename}]: Found '{match.group()}'\n"
                f"     Reason: {reason}\n"
                f"     Fix: Add test method, dates, and reproducibility proof"
            )
    return issues


def check_structure(filepath: Path, content: str) -> list[str]:
    """Check memory file structure."""
    issues = []

    # Parse frontmatter
    if not content.startswith("---"):
        issues.append("  [FAIL] Missing frontmatter (---)")
        return issues

    frontmatter_end = content.find("---", 3)
    if frontmatter_end == -1:
        issues.append("  [FAIL] Malformed frontmatter (no closing ---)")
        return issues

    frontmatter = content[3:frontmatter_end]

    # Check for metadata type
    type_match = re.search(r"type:\s*(\w+)", frontmatter)
    if not type_match:
        issues.append("  [FAIL] Missing 'type:' field in frontmatter")
        return issues

    mem_type = type_match.group(1)

    # For session files: always fail
    if filepath.name.startswith("session_"):
        issues.append(
            "  [FAIL] Session memory files are banned\n"
            "     Reason: Status files rot and become false\n"
            "     Fix: Keep specific bugs/rules instead, not session summaries"
        )
        return issues

    # For tested claims: require test method
    if "tested" in content.lower() or "verified" in content.lower():
        lowered = content.lower()
        # BUG FOUND 2026-08-11: this originally only matched an exact keyword substring
        # ("command:", "verified via", etc). In practice, a real verification writeup rarely
        # uses those literal phrases - it names the actual pytest/script invocation and its
        # result ("`python -m pytest ... -q` (7 passed)", "exit 0, 9/9 phases"). That pattern
        # is at least as strong evidence of real verification as the original keyword list,
        # but the exact-substring check flagged it as unverified anyway - a false positive hit
        # repeatedly during a single concurrent-heavy session, each time blocking commits
        # repo-wide (this check is always_run against the whole memory dir, not just staged
        # files) for a claim that was, on inspection, genuinely backed by a shown command and
        # result. Widened to also recognize inline/fenced code (a shown command) paired with a
        # pytest-style result line, without weakening the underlying requirement that SOME
        # concrete evidence be present.
        has_method = any(
            keyword in lowered
            for keyword in [
                "command:",
                "method:",
                "how:",
                "ran",
                "executed",
                "test:",
                "verification:",
                "verified on:",
                "verified via",
                "pytest",
                "exit 0",
                "exit code",
            ]
        )
        if not has_method:
            has_shown_command = bool(re.search(r"`[^`\n]+`", content))
            has_result_line = bool(re.search(r"\d+\s*(passed|/\d+)", lowered))
            has_method = has_shown_command and has_result_line
        if not has_method:
            issues.append(
                "  [FAIL] Claims tested/verified but no test method shown\n"
                "     Fix: Show exact command/code run, date, result"
            )

    # For feedback type: require Why and How to apply
    if mem_type == "feedback":
        if "**Why:**" not in content and "**why:**" not in content:
            issues.append(
                "  [FAIL] Feedback missing '**Why:**' section\n     Required: Explain the bug or reason for this rule"
            )
        if "**How to apply:**" not in content and "**how to apply:**" not in content:
            issues.append(
                "  [FAIL] Feedback missing '**How to apply:**' section\n     Required: Explain when/how to use this rule"
            )

    return issues


def check_memory_staleness() -> list[str]:
    """Check for stale memory without recent verification."""
    issues = []

    # Get files modified more than 14 days ago
    cutoff = datetime.now() - timedelta(days=14)

    for filepath in MEMORY_DIR.glob("*.md"):
        if filepath.name in ["MEMORY.md", "memory_safety_protocol.md"]:
            continue

        stat = filepath.stat()
        mod_time = datetime.fromtimestamp(stat.st_mtime)

        if mod_time < cutoff:
            # Check if it has a "verified" or "tested" claim. utf-8-sig (see check_structure's
            # matching fix below for the full rationale) so a BOM-prefixed file's content
            # doesn't start with a stray BOM character.
            content = filepath.read_text(encoding="utf-8-sig", errors="replace")
            if any(word in content.lower() for word in ["tested:", "verified:", "method:"]):
                age_days = (datetime.now() - mod_time).days
                issues.append(
                    f"  [WARN]  Stale memory ({age_days} days old): {filepath.name}\n"
                    f"     Fix: Re-verify this memory is still accurate or delete it"
                )

    return issues


def validate_all() -> tuple[int, list[str]]:
    """Validate all memory files."""
    all_issues = []

    print("\n" + "=" * 70)
    print("MEMORY SAFETY VALIDATION")
    print("=" * 70 + "\n")

    if not MEMORY_DIR.exists():
        # Memory lives outside the repo (~/.claude/projects/.../memory), so it never exists on
        # a CI runner or a fresh checkout - that's "nothing to validate", not a violation. This
        # used to return 1 here, unconditionally failing CI's "validate" job on every push since
        # this script was wired in (5a20388c0, 2026-07-31) - hidden behind the ruff/mypy pin
        # failures until those were fixed, at which point this became the real blocker.
        print(f"Memory directory not found: {MEMORY_DIR} (nothing to validate)")
        return 0, []

    # Check all .md files
    md_files = sorted(MEMORY_DIR.glob("*.md"))
    if not md_files:
        print(f"No memory files found in {MEMORY_DIR}")
        return 0, []

    print(f"Checking {len(md_files)} memory files...\n")

    files_with_issues = 0
    for filepath in md_files:
        # utf-8-sig (not plain utf-8) strips a leading BOM if present, falling back to
        # normal utf-8 otherwise - ROOT-CAUSE FIX 2026-08-17: a BOM-prefixed memory file
        # (e.g. written by PowerShell's Out-File, which defaults to UTF-8-with-BOM) read as
        # "﻿---\n..." under plain utf-8, so `content.startswith("---")` below false-failed
        # a structurally-valid file as "Missing frontmatter", blocking every commit repo-wide
        # via this validator's pre-commit hook - live-reproduced on
        # scheduler_lock_owner_liveness_check_fix_20260817.md.
        content = filepath.read_text(encoding="utf-8-sig", errors="replace")
        issues = []

        # Skip checking documentation/teaching files (they intentionally contain examples of bad memory)
        skip_files = {
            "MEMORY.md",
            "memory_safety_protocol.md",
            "memory_template_good_examples.md",
            "feedback_memory_checklist_enforcement.md",  # teaching file about checklist
            "feedback_memory_verification.md",  # teaching file about verification
            "feedback_verify_claims_before_memory.md",  # teaching file about claims
        }
        if filepath.name in skip_files:
            print(f"[SKIP] {filepath.name} (documentation - skipped)")
            continue

        issues.extend(check_red_flags(content, filepath.name))
        issues.extend(check_structure(filepath, content))

        if issues:
            files_with_issues += 1
            print(f"[FAIL] {filepath.name}")
            for issue in issues:
                print(issue)
            print()
        else:
            print(f"[OK] {filepath.name}")

    # Check staleness
    print("\nChecking for stale memory...\n")
    stale_issues = check_memory_staleness()
    all_issues.extend(stale_issues)

    for issue in stale_issues:
        print(issue)
        print()

    print("\n" + "=" * 70)
    if files_with_issues or stale_issues:
        print(f"FAILED: {files_with_issues} files with issues + {len(stale_issues)} stale")
        print("=" * 70 + "\n")
        return 1, all_issues
    else:
        print("PASSED: All memory files meet safety standards")
        print("=" * 70 + "\n")
        return 0, []


if __name__ == "__main__":
    exit_code, issues = validate_all()
    sys.exit(exit_code)
