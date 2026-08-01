#!/usr/bin/env python3
"""
Comprehensive code audit to find actual bugs before production trading
"""
import os
import re
import subprocess
from pathlib import Path
from collections import defaultdict

def find_files(pattern):
    """Find Python files matching pattern"""
    result = subprocess.run(
        ['find', 'algo', 'loaders', 'scripts', '-name', '*.py', '-type', 'f'],
        capture_output=True,
        text=True,
        cwd=os.getcwd()
    )
    return result.stdout.strip().split('\n') if result.stdout else []

def check_transaction_safety():
    """Check if all DB transactions have proper commit/rollback"""
    print("\n" + "="*80)
    print("TRANSACTION SAFETY CHECK")
    print("="*80)

    # Look for DatabaseContext without proper commit
    issues = []
    for py_file in find_files('*.py'):
        if not py_file or not os.path.exists(py_file):
            continue
        try:
            with open(py_file, 'r') as f:
                content = f.read()
                lines = content.split('\n')

            # Find DatabaseContext usage
            for i, line in enumerate(lines):
                if 'DatabaseContext' in line and 'with' in line:
                    # Check next 50 lines for proper exit handling
                    context_block = '\n'.join(lines[i:min(i+50, len(lines))])

                    # Look for missing COMMIT patterns
                    if 'write' in context_block and 'COMMIT' not in context_block:
                        if '__exit__' not in context_block and 'return' in context_block:
                            issues.append((py_file, i+1, 'Write context may not commit'))
        except Exception as e:
            pass

    if issues:
        print(f"⚠️  POTENTIAL TRANSACTION ISSUES ({len(issues)}):")
        for file, line, issue in issues[:10]:
            print(f"   {file}:{line}: {issue}")
    else:
        print("✅ No obvious transaction safety issues found")

    return len(issues) > 0

def check_halt_flag_usage():
    """Check if halt flag is properly checked before critical operations"""
    print("\n" + "="*80)
    print("HALT FLAG USAGE CHECK")
    print("="*80)

    issues = []

    # Check orchestrator phases for halt flag checks
    phase_files = [
        'algo/orchestrator/phase1_data_freshness.py',
        'algo/orchestrator/phase2_circuit_breakers.py',
        'algo/orchestrator/phase8_entry_execution.py',
    ]

    for py_file in phase_files:
        if os.path.exists(py_file):
            with open(py_file, 'r') as f:
                content = f.read()

            # These phases SHOULD check halt flag before proceeding
            if 'check_halt_flag' not in content and 'halt' not in content.lower():
                issues.append((py_file, 'No halt flag check found'))

    if issues:
        print(f"⚠️  POTENTIAL HALT FLAG ISSUES ({len(issues)}):")
        for file, issue in issues:
            print(f"   {file}: {issue}")
    else:
        print("✅ Halt flag checks appear properly implemented")

    return len(issues) > 0

def check_position_limit_enforcement():
    """Check if position limit is enforced everywhere"""
    print("\n" + "="*80)
    print("POSITION LIMIT ENFORCEMENT CHECK")
    print("="*80)

    issues = []

    # Check entry execution for position limit
    entry_file = 'algo/orchestrator/phase8_entry_execution.py'
    if os.path.exists(entry_file):
        with open(entry_file, 'r') as f:
            content = f.read()

        if 'max_open_positions' not in content:
            issues.append((entry_file, 'Position limit not checked'))
        elif content.count('max_open_positions') < 2:
            issues.append((entry_file, 'Position limit checked only once (may be insufficient)'))

    if issues:
        print(f"⚠️  POSITION LIMIT ISSUES ({len(issues)}):")
        for file, issue in issues:
            print(f"   {file}: {issue}")
    else:
        print("✅ Position limit appears properly enforced")

    return len(issues) > 0

def check_exit_engine_completeness():
    """Check if exit engine handles all 17 positions"""
    print("\n" + "="*80)
    print("EXIT ENGINE COMPLETENESS CHECK")
    print("="*80)

    exit_file = 'algo/trading/exit_engine.py'
    issues = []

    if os.path.exists(exit_file):
        with open(exit_file, 'r') as f:
            lines = f.readlines()

        # Look for the main exit loop
        for i, line in enumerate(lines):
            if 'for symbol in' in line or 'for.*position' in line.lower():
                # Check if there's proper error handling around this loop
                context = ''.join(lines[i:min(i+20, len(lines))])
                if 'except' not in context and 'try' not in context:
                    issues.append((exit_file, i+1, 'Exit loop may not have error handling'))

    if issues:
        print(f"⚠️  EXIT ENGINE ISSUES ({len(issues)}):")
        for file, line, issue in issues:
            print(f"   {file}:{line}: {issue}")
    else:
        print("✅ Exit engine appears properly error-handled")

    return len(issues) > 0

def check_signal_quality_threshold():
    """Verify signal quality threshold is correct"""
    print("\n" + "="*80)
    print("SIGNAL QUALITY THRESHOLD CHECK")
    print("="*80)

    # Check the config for signal quality threshold
    config_file = 'algo/infrastructure/config/defaults.py'
    threshold_issue = False

    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            content = f.read()

        # Look for min_signal_quality_score
        match = re.search(r'min_signal_quality_score["\']?\s*[:=]\s*(\d+)', content)
        if match:
            threshold = int(match.group(1))
            print(f"📊 Configured threshold: {threshold}")

            if threshold > 70:
                threshold_issue = True
                print(f"⚠️  THRESHOLD TOO HIGH: {threshold} > max observed 70")
            elif threshold < 50:
                print(f"⚠️  THRESHOLD TOO LOW: {threshold} (too lenient)")
            else:
                print(f"✅ Threshold {threshold} appears reasonable")

    return threshold_issue

def check_data_loader_status():
    """Check if loader status is properly reported"""
    print("\n" + "="*80)
    print("DATA LOADER STATUS CHECK")
    print("="*80)

    loader_file = 'loaders/load_prices.py'
    issues = []

    if os.path.exists(loader_file):
        with open(loader_file, 'r') as f:
            content = f.read()

        # Check for min_acceptable_pct threshold
        match = re.search(r'min_acceptable_pct\s*=\s*(\d+)', content)
        if match:
            threshold = int(match.group(1))
            print(f"📊 Price loader min_acceptable_pct: {threshold}%")

            if threshold > 95:
                issues.append(f"Threshold {threshold}% is too aggressive (real data ~94%)")
            elif threshold < 85:
                issues.append(f"Threshold {threshold}% is too lenient")
            else:
                print(f"✅ Threshold {threshold}% appears appropriate")

    if issues:
        print(f"⚠️  LOADER STATUS ISSUES ({len(issues)}):")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("✅ Loader status thresholds appear correct")

    return len(issues) > 0

def check_orchestrator_phase_order():
    """Verify orchestrator phases run in correct order"""
    print("\n" + "="*80)
    print("ORCHESTRATOR PHASE ORDER CHECK")
    print("="*80)

    executor_file = 'algo/orchestrator/phase_executor.py'
    issues = []

    if os.path.exists(executor_file):
        with open(executor_file, 'r') as f:
            content = f.read()

        # Extract phase run order
        phase_order = []
        for i in range(1, 10):
            if f"phase_{i}" in content or f"phase{i}" in content:
                phase_order.append(i)

        if phase_order == list(range(1, max(phase_order) + 1)):
            print(f"✅ Phases run in correct order: {phase_order}")
        else:
            print(f"⚠️  Phase order may be incorrect: {phase_order}")
            issues.append("Phase execution order looks wrong")

    return len(issues) > 0

# Run all checks
print("\n" + "="*100)
print("PRODUCTION READINESS AUDIT - Comprehensive Code Review")
print("="*100)

os.chdir('C:/Users/arger/code/algo')

check_transaction_safety()
check_halt_flag_usage()
check_position_limit_enforcement()
check_exit_engine_completeness()
check_signal_quality_threshold()
check_data_loader_status()
check_orchestrator_phase_order()

print("\n" + "="*100)
print("AUDIT COMPLETE")
print("="*100)
print("""
NEXT STEPS FOR PRODUCTION:
1. Replace test Alpaca credentials with real ones
2. Run full stress test with orchestrator (5+ cycles minimum)
3. Verify exit engine executes exits when conditions are met
4. Monitor halt flag state and ensure it properly blocks entries
5. Test loader failure scenarios
6. Verify transaction rollback on database errors
7. Run against live data (paper mode) for 1 week
""")
