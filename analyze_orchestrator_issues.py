#!/usr/bin/env python
"""
Analyze orchestrator log for issues, warnings, and potential bypasses
"""
import re
from collections import defaultdict

log_file = 'orchestrator_force_run.log'

# Categories of issues to find
issues = defaultdict(list)

with open(log_file, 'r') as f:
    for line_num, line in enumerate(f, 1):
        # Find all WARNING and ERROR messages
        if 'WARNING' in line or 'ERROR' in line or 'FATAL' in line:
            issues['warnings'].append((line_num, line.strip()[:150]))

        # Find specific bypasses or skips
        if any(x in line for x in ['skipping', 'skip', 'skipped', 'bypass', 'ignore', 'unavailable', 'fallback']):
            if 'WARNING' in line or 'ERROR' in line:
                issues['bypasses'].append((line_num, line.strip()[:150]))

        # Find paper mode notes
        if 'paper' in line.lower() and ('mode' in line.lower() or 'trading' in line.lower()):
            if 'active' in line.lower():
                issues['paper_mode'].append((line_num, line.strip()[:150]))

        # Find 404 errors
        if '404' in line:
            issues['api_errors'].append((line_num, line.strip()[:150]))

print("=" * 100)
print("ORCHESTRATOR LOG ANALYSIS - Issues & Bypasses")
print("=" * 100)

print(f"\n📊 WARNINGS & ERRORS FOUND: {len(issues['warnings'])}")
if issues['warnings'][:5]:
    for line_num, msg in issues['warnings'][:5]:
        print(f"  Line {line_num}: {msg}")
    if len(issues['warnings']) > 5:
        print(f"  ... and {len(issues['warnings']) - 5} more")

print(f"\n🔄 BYPASSES & FALLBACKS: {len(issues['bypasses'])}")
for line_num, msg in issues['bypasses']:
    print(f"  Line {line_num}: {msg}")

print(f"\n📄 PAPER MODE NOTES: {len(issues['paper_mode'])}")
for line_num, msg in issues['paper_mode'][:3]:
    print(f"  Line {line_num}: {msg}")

print(f"\n❌ API ERRORS (404s): {len(issues['api_errors'])}")
if issues['api_errors']:
    print(f"  {len(issues['api_errors'])} symbols returned 404 from Alpaca")

# Now check for actual bugs in the codebase related to these issues
print("\n" + "=" * 100)
print("CHECKING CODE FOR ISSUES")
print("=" * 100)

import subprocess
import os

os.chdir('C:/Users/arger/code/algo')

# Check for common bypass patterns
bypass_patterns = [
    (r'\.get\([^,]+,\s*[^)]*\)', 'Dangerous .get() pattern - masks missing data'),
    (r'pass\s*#\s*TODO|pass\s*#\s*FIXME', 'TODO/FIXME with pass - incomplete code'),
    (r'if.*:\s*continue\s*#.*skip', 'Skipping checks - potential bypass'),
    (r'# bypass|# skip|# ignore', 'Explicit bypass comments'),
    (r'except.*:\s*pass', 'Silent exception catching'),
]

print("\n🔍 Scanning code for bypass patterns...\n")

found_issues = False
for pattern, description in bypass_patterns:
    try:
        result = subprocess.run(
            ['grep', '-r', '-E', pattern, 'algo/', 'loaders/', 'scripts/', 'config/'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.stdout:
            found_issues = True
            print(f"⚠️  {description}")
            lines = result.stdout.strip().split('\n')[:3]
            for line in lines:
                if line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        print(f"   {parts[0]}: {(':'.join(parts[1:]))[:80]}")
            stdout_lines = result.stdout.strip().split('\n')
            if len(stdout_lines) > 3:
                remaining = len(stdout_lines) - 3
                print(f"   ... and {remaining} more")
            print()
    except Exception as e:
        pass

if not found_issues:
    print("✅ No obvious bypass patterns found in code scan")

print("\n" + "=" * 100)
print("RECOMMENDATIONS FOR PRODUCTION READINESS")
print("=" * 100)

recommendations = [
    "1. Verify Phase 6 exit decisions: Check exit_engine output for correctness",
    "2. Test position sizing limits: Ensure 17-position limit is enforced properly",
    "3. Validate signal quality scores: Confirm 60-point threshold is appropriate",
    "4. Check halt flags: Ensure halt system works with real RDS (not just local)",
    "5. Verify transaction safety: Check all DB writes have proper COMMIT/ROLLBACK",
    "6. Test loader failures: Simulate data loader failures and verify orchestrator handles it",
    "7. Check Alpaca integration: Replace paper mode credentials with real ones before production",
]

for rec in recommendations:
    print(f"  {rec}")
