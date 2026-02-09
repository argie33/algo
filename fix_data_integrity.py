#!/usr/bin/env python3
"""
DATA INTEGRITY FIX SCRIPT
Systematic cleanup of all loader files for fake data, NULL corruption, and bounds issues
Executed: 2026-02-09
"""

import os
import re
import sys

# Track changes
changes_made = {}

def fix_fake_dates(filepath):
    """Remove date.today() fake date insertion - replace with NULL or real data"""
    with open(filepath, 'r') as f:
        content = f.read()

    original = content
    file_changes = 0

    # Pattern 1: 'date': date.today() → NULL fallback
    pattern1 = r"'date':\s*date\.today\(\)"
    replacement1 = "'date': None  # FIXED: Removed fake date.today() - use real data date or NULL"
    content = re.sub(pattern1, replacement1, content)
    if content != original:
        file_changes += re.findall(pattern1, original).__len__()

    # Pattern 2: date.today() as fallback in conditionals
    pattern2 = r"else:\s*\n\s*.*?=\s*date\.today\(\)"
    if re.search(pattern2, content):
        # Mark for manual review
        content = content.replace("date.today()", "None  # FIXED: Removed fake date - needs manual review to use real data")
        file_changes += 1

    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        return file_changes
    return 0

def fix_null_corruption(filepath):
    """Replace str(get()) with safe_str()"""
    with open(filepath, 'r') as f:
        content = f.read()

    original = content
    file_changes = 0

    # Pattern: str(row.get(...)) → safe_str(row.get(...))
    # But only for DataFrames operations
    pattern = r"str\(([^)]*\.get\([^)]*\))\)"
    matches = re.findall(pattern, content)

    for match in matches:
        if '.get' in match:
            old = f"str({match})"
            new = f"safe_str({match})"
            content = content.replace(old, new)
            file_changes += 1

    if content != original:
        # Make sure safe_str is imported
        if 'from lib.db import safe_str' not in content and 'def safe_str' not in content:
            # Add import if not present
            if 'import' in content:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if line.startswith('import') or line.startswith('from'):
                        if i < len(lines) - 1 and (lines[i+1].startswith('import') or lines[i+1].startswith('from')):
                            continue
                        else:
                            lines.insert(i+1, 'from lib.db import safe_str')
                            break
                content = '\n'.join(lines)

        with open(filepath, 'w') as f:
            f.write(content)
        return file_changes
    return 0

def fix_bounds_clamping(filepath):
    """Increase bounds that are too restrictive"""
    with open(filepath, 'r') as f:
        content = f.read()

    original = content
    file_changes = 0

    # Fix growth rate bounds: max_val=100 → 10000
    replacements = [
        (r'max_val=100([,\)])', r'max_val=10000\1', 'earningsGrowth|revenueGrowth|Growth'),
        (r'max_val=99\.99([,\)])', r'max_val=10000\1', 'Yield|yield'),
        (r'max_val=10,', 'max_val=100,', 'beta'),
        (r'min_val=-5([,\)])', r'min_val=-10\1', 'beta'),
    ]

    for pattern, replacement, description in replacements:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            file_changes += len(re.findall(pattern, content))
            content = new_content

    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        return file_changes
    return 0

# Main execution
print("=" * 80)
print("DATA INTEGRITY FIX - SYSTEMATIC CLEANUP")
print("=" * 80)

loader_files = [
    'loaddailycompanydata.py',  # Already mostly fixed
    'loadcalendar.py',
    'loadcoveredcallopportunities.py',
    'loadfactormetrics.py',
    'loadmarket.py',
    'loadoptionschains.py',
    'loadsentiment.py',
]

total_changes = 0

for filepath in loader_files:
    if not os.path.exists(filepath):
        print(f"⚠️  {filepath} NOT FOUND - skipping")
        continue

    file_total = 0

    # Fix 1: Remove fake dates
    fake_date_fixes = fix_fake_dates(filepath)
    if fake_date_fixes:
        print(f"✅ {filepath}: Removed {fake_date_fixes} fake date.today() instances")
        file_total += fake_date_fixes

    # Fix 2: Fix NULL handling
    null_fixes = fix_null_corruption(filepath)
    if null_fixes:
        print(f"✅ {filepath}: Fixed {null_fixes} str(get()) NULL corruption issues")
        file_total += null_fixes

    # Fix 3: Fix bounds
    bounds_fixes = fix_bounds_clamping(filepath)
    if bounds_fixes:
        print(f"✅ {filepath}: Fixed {bounds_fixes} bounds clamping issues")
        file_total += bounds_fixes

    if file_total == 0:
        print(f"✔️  {filepath}: No issues found")

    total_changes += file_total

print("=" * 80)
print(f"TOTAL FIXES APPLIED: {total_changes}")
print("=" * 80)
print("\n⚠️  IMPORTANT: Review all changes with git diff before committing")
print("Some changes may need manual review for correctness")
print("\nNext steps:")
print("1. Review changes: git diff")
print("2. Test with sample data")
print("3. Commit changes")
