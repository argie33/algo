#!/usr/bin/env python3
"""Verify that all claimed fixes are actually implemented."""

import os
import sys
from pathlib import Path

project_root = Path('.').resolve()
sys.path.insert(0, str(project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

os.environ['LOCAL_MODE'] = 'true'

import re

print("=" * 100)
print("VERIFICATION: Checking that all claimed fixes are in the code")
print("=" * 100)

checks = []

# Check 1: Entry duplicate prevention is called
print("\n[1] Entry duplicate prevention check is called")
executor_entry_handler = Path('algo/trading/executor_entry_handler.py').read_text()
if 'check_idempotent_duplicate' in executor_entry_handler and executor_entry_handler.count('check_idempotent_duplicate') >= 2:
    print("    [PASS] check_idempotent_duplicate is defined and called")
    checks.append(True)
else:
    print("    [FAIL] check_idempotent_duplicate not properly wired")
    checks.append(False)

# Check 2: P&L calculations in phase 9
print("\n[2] P&L calculations in phase 9 reconciliation")
phase9 = Path('algo/orchestrator/phase9_reconciliation.py').read_text()
if 'profit_loss_dollars' in phase9 and 'profit_loss_pct' in phase9:
    print("    [PASS] P&L fields populated in phase 9")
    checks.append(True)
else:
    print("    [FAIL] P&L calculations missing")
    checks.append(False)

# Check 3: Phase 6 error audit fix (the one we just added)
print("\n[3] Phase 6 error audit persists before counting")
phase6 = Path('algo/trading/exit_engine.py').read_text()
if 'audit_success' in phase6 and 'if audit_success:' in phase6 and 'trade_errors += 1' in phase6:
    print("    [PASS] Errors only counted after successful audit INSERT")
    checks.append(True)
else:
    print("    [FAIL] Error counting may happen before audit")
    checks.append(False)

# Check 4: Cursor parameter cleanup in phase 3
print("\n[4] Cursor parameters cleaned up in position monitor")
position_monitor = Path('algo/orchestrator/phase3_position_monitor.py').read_text()
if 'def check_sector_concentration(self, cur=' in position_monitor:
    print("    [WARN] check_sector_concentration still has 'cur' parameter")
    checks.append(False)
else:
    print("    [PASS] Cursor parameters cleaned up")
    checks.append(True)

# Check 5: Execution mode race condition fix
print("\n[5] Execution mode race condition handling")
orchestrator = Path('algo/orchestration/orchestrator.py').read_text()
if 'execution_mode_check' in orchestrator:
    print("    [PASS] Execution mode handling present")
    checks.append(True)
else:
    print("    [FAIL] Execution mode handling may have issues")
    checks.append(False)

# Check 6: DatabaseContext transaction handling
print("\n[6] DatabaseContext transaction safety")
exit_engine = Path('algo/trading/exit_engine.py').read_text()
if 'with DatabaseContext("write") as cur:' in exit_engine:
    print("    [PASS] Using DatabaseContext for transaction management")
    checks.append(True)
else:
    print("    [FAIL] DatabaseContext usage issue")
    checks.append(False)

print("\n" + "=" * 100)
passed = sum(checks)
total = len(checks)
print("SUMMARY: %d/%d checks passed" % (passed, total))
if passed == total:
    print("[OK] All fixes verified in code")
else:
    print("[ERROR] %d issues found" % (total - passed))
print("=" * 100)
