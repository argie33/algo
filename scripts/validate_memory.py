#!/usr/bin/env python3
"""
Memory validation script - enforces safety standards before memory is accepted.
Runs before any memory write to catch violations.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple
from datetime import datetime, timedelta

# Fix encoding on Windows (but not during pytest)
if sys.stdout.encoding and 'utf' not in sys.stdout.encoding.lower() and "pytest" not in sys.modules:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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

def check_red_flags(content: str, filename: str) -> List[str]:
    """Check for unverified claims."""
    issues = []
    for pattern, reason in RED_FLAGS.items():
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            line_num = content[:match.start()].count('\n') + 1
            issues.append(
                f"  ❌ Line {line_num} [{filename}]: Found '{match.group()}'\n"
                f"     Reason: {reason}\n"
                f"     Fix: Add test method, dates, and reproducibility proof"
            )
    return issues

def check_structure(filepath: Path, content: str) -> List[str]:
    """Check memory file structure."""
    issues = []

    # Parse frontmatter
    if not content.startswith("---"):
        issues.append(f"  ❌ Missing frontmatter (---)")
        return issues

    frontmatter_end = content.find("---", 3)
    if frontmatter_end == -1:
        issues.append(f"  ❌ Malformed frontmatter (no closing ---)")
        return issues

    frontmatter = content[3:frontmatter_end]
    body = content[frontmatter_end+3:].strip()

    # Check for metadata type
    type_match = re.search(r"type:\s*(\w+)", frontmatter)
    if not type_match:
        issues.append(f"  ❌ Missing 'type:' field in frontmatter")
        return issues

    mem_type = type_match.group(1)

    # For session files: always fail
    if filepath.name.startswith("session_"):
        issues.append(
            f"  ❌ Session memory files are banned\n"
            f"     Reason: Status files rot and become false\n"
            f"     Fix: Keep specific bugs/rules instead, not session summaries"
        )
        return issues

    # For tested claims: require test method
    if "tested" in content.lower() or "verified" in content.lower():
        has_method = any(
            keyword in content.lower()
            for keyword in ["command:", "method:", "how:", "ran", "executed", "test:",
                           "verification:", "verified on:", "verified via"]
        )
        if not has_method:
            issues.append(
                f"  ❌ Claims tested/verified but no test method shown\n"
                f"     Fix: Show exact command/code run, date, result"
            )

    # For feedback type: require Why and How to apply
    if mem_type == "feedback":
        if "**Why:**" not in content and "**why:**" not in content:
            issues.append(
                f"  ❌ Feedback missing '**Why:**' section\n"
                f"     Required: Explain the bug or reason for this rule"
            )
        if "**How to apply:**" not in content and "**how to apply:**" not in content:
            issues.append(
                f"  ❌ Feedback missing '**How to apply:**' section\n"
                f"     Required: Explain when/how to use this rule"
            )

    return issues

def check_memory_staleness() -> List[str]:
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
            # Check if it has a "verified" or "tested" claim
            content = filepath.read_text(encoding='utf-8', errors='replace')
            if any(word in content.lower() for word in ["tested:", "verified:", "method:"]):
                age_days = (datetime.now() - mod_time).days
                issues.append(
                    f"  ⚠️  Stale memory ({age_days} days old): {filepath.name}\n"
                    f"     Fix: Re-verify this memory is still accurate or delete it"
                )

    return issues

def validate_all() -> Tuple[int, List[str]]:
    """Validate all memory files."""
    all_issues = []

    print("\n" + "="*70)
    print("MEMORY SAFETY VALIDATION")
    print("="*70 + "\n")

    if not MEMORY_DIR.exists():
        print(f"Memory directory not found: {MEMORY_DIR}")
        return 1, []

    # Check all .md files
    md_files = sorted(MEMORY_DIR.glob("*.md"))
    if not md_files:
        print(f"No memory files found in {MEMORY_DIR}")
        return 0, []

    print(f"Checking {len(md_files)} memory files...\n")

    files_with_issues = 0
    for filepath in md_files:
        content = filepath.read_text(encoding='utf-8', errors='replace')
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
            print(f"⊘ {filepath.name} (documentation - skipped)")
            continue

        issues.extend(check_red_flags(content, filepath.name))
        issues.extend(check_structure(filepath, content))

        if issues:
            files_with_issues += 1
            print(f"❌ {filepath.name}")
            for issue in issues:
                print(issue)
            print()
        else:
            print(f"✅ {filepath.name}")

    # Check staleness
    print("\nChecking for stale memory...\n")
    stale_issues = check_memory_staleness()
    all_issues.extend(stale_issues)

    for issue in stale_issues:
        print(issue)
        print()

    print("\n" + "="*70)
    if files_with_issues or stale_issues:
        print(f"FAILED: {files_with_issues} files with issues + {len(stale_issues)} stale")
        print("="*70 + "\n")
        return 1, all_issues
    else:
        print("PASSED: All memory files meet safety standards")
        print("="*70 + "\n")
        return 0, []

if __name__ == "__main__":
    exit_code, issues = validate_all()
    sys.exit(exit_code)
