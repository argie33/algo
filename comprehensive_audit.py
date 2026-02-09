#!/usr/bin/env python3
"""
COMPREHENSIVE SYSTEM AUDIT
Scans all 58 loader files for data integrity issues
Generates complete fix plan
"""

import os
import re
from pathlib import Path
from collections import defaultdict

# Initialize findings
findings = {
    'fake_dates': [],
    'null_corruption': [],
    'bounds_issues': [],
    'schema_mismatches': [],
    'fallback_logic': [],
    'other_issues': []
}

loader_files = [f for f in os.listdir('.') if f.startswith('load') and f.endswith('.py')]
loader_files.sort()

print("=" * 100)
print("COMPREHENSIVE DATA INTEGRITY AUDIT - ALL 58 LOADER FILES")
print("=" * 100)
print(f"\nScanning {len(loader_files)} loader files...\n")

for filepath in loader_files:
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            lines = content.split('\n')

        file_issues = defaultdict(list)

        # 1. FAKE DATE DETECTION
        for i, line in enumerate(lines, 1):
            if 'date.today()' in line:
                file_issues['fake_dates'].append({
                    'file': filepath,
                    'line': i,
                    'code': line.strip()[:80]
                })

            # 2. NULL CORRUPTION DETECTION
            if re.search(r"str\([^)]*\.get\(", line):
                # Exclude cases with defaults like str(x.get('field', ''))
                if ".get('" in line and ", '" in line:
                    continue
                file_issues['null_corruption'].append({
                    'file': filepath,
                    'line': i,
                    'code': line.strip()[:80]
                })

            # 3. BOUNDS CLAMPING ISSUES
            # Check for restrictive max_val bounds
            if 'max_val=' in line:
                # Find all max_val patterns
                bounds = re.findall(r'max_val=(\d+)', line)
                for bound in bounds:
                    if int(bound) in [100, 99, 10]:  # Suspiciously low
                        if any(x in line for x in ['growth', 'Growth', 'yield', 'Yield', 'beta', 'Beta', 'ROE', 'roe']):
                            file_issues['bounds_issues'].append({
                                'file': filepath,
                                'line': i,
                                'code': line.strip()[:80],
                                'bound': bound
                            })

            # 4. SCHEMA MISMATCH DETECTION
            if 'INSERT INTO' in line and '%s' in line:
                # Check if it's using 'ticker' or 'symbol'
                if 'ticker' in line.lower() and 'symbol' in lines[i] if i < len(lines) else False:
                    file_issues['schema_mismatches'].append({
                        'file': filepath,
                        'line': i,
                        'code': line.strip()[:80]
                    })

            # 5. FALLBACK/CALCULATED DATA LOGIC
            if any(x in line for x in ['calculate', 'fallback', 'estimate', ' or ', 'default']):
                if 'def ' not in line and 'comment' not in line.lower():
                    if re.search(r'\bor\s+\w+\.get\(', line):
                        file_issues['fallback_logic'].append({
                            'file': filepath,
                            'line': i,
                            'code': line.strip()[:80]
                        })

        # Report file issues
        has_issues = any(file_issues.values())
        if has_issues:
            print(f"🔴 {filepath}")
            for issue_type, issues in file_issues.items():
                if issues:
                    print(f"   ├─ {issue_type}: {len(issues)} instance(s)")
                    for issue in issues[:2]:  # Show first 2
                        print(f"   │  └─ Line {issue['line']}: {issue['code']}")
                    if len(issues) > 2:
                        print(f"   │  └─ ... and {len(issues)-2} more")

            # Add to global findings
            for issue_type, issues in file_issues.items():
                findings[issue_type].extend(issues)
        else:
            print(f"✅ {filepath}")

    except Exception as e:
        print(f"⚠️  {filepath}: Error scanning - {str(e)[:50]}")

print("\n" + "=" * 100)
print("AUDIT SUMMARY")
print("=" * 100)

total_issues = sum(len(v) for v in findings.values())
print(f"\nTotal Issues Found: {total_issues}")
print(f"\nBreakdown:")
print(f"  • Fake Dates (date.today()): {len(findings['fake_dates'])}")
print(f"  • NULL Corruption (str(get())): {len(findings['null_corruption'])}")
print(f"  • Bounds Clamping Issues: {len(findings['bounds_issues'])}")
print(f"  • Schema Mismatches: {len(findings['schema_mismatches'])}")
print(f"  • Fallback/Calculate Logic: {len(findings['fallback_logic'])}")

print(f"\nAffected Files: {len(set(issue['file'] for issues in findings.values() for issue in issues))} out of {len(loader_files)}")

print("\n" + "=" * 100)
print("FILES NEEDING FIXES (Priority Order)")
print("=" * 100)

affected_files = defaultdict(int)
for issue_type, issues in findings.items():
    for issue in issues:
        affected_files[issue['file']] += 1

for filepath in sorted(affected_files.keys(), key=lambda x: affected_files[x], reverse=True):
    count = affected_files[filepath]
    print(f"🔴 {filepath}: {count} issue(s)")

print("\n" + "=" * 100)
print("STATUS: AUDIT COMPLETE - Ready for systematic fixes")
print("=" * 100)
