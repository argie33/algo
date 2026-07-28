#!/usr/bin/env python3
"""Comprehensive audit: Run orchestrator and collect all errors/warnings for systematic analysis."""

import sys
sys.path.insert(0, ".")

import logging
import json
from datetime import date
from collections import defaultdict

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s:%(name)s:%(message)s'
)

# Capture all log messages
all_logs = []
error_count = defaultdict(int)
warning_count = defaultdict(int)


class AuditHandler(logging.Handler):
    def emit(self, record):
        all_logs.append({
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'lineno': record.lineno,
        })

        if record.levelname == 'ERROR':
            error_count[record.module] += 1
        elif record.levelname == 'WARNING':
            warning_count[record.module] += 1


# Add handler to root logger
audit_handler = AuditHandler()
logging.getLogger().addHandler(audit_handler)

print("=" * 80)
print("ORCHESTRATOR COMPREHENSIVE AUDIT - Starting...")
print("=" * 80)

try:
    from algo.orchestration.orchestrator import Orchestrator
    from algo.infrastructure.config import AlgoConfig
    import uuid

    config = AlgoConfig()

    # Run orchestrator with dry_run to bypass market hours
    print("\n[TEST] Running orchestrator in dry_run mode...")
    run_id = f"AUDIT-{date.today()}-{uuid.uuid4().hex[:8]}"
    orch = Orchestrator(
        config=config,
        run_id=run_id,
        dry_run=True,
    )
    result = orch.run()

    print(f"\n[RESULT] Orchestrator completed: {result}")

except Exception as e:
    print(f"\n[ERROR] Orchestrator failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# Print summary
print("\n" + "=" * 80)
print("AUDIT SUMMARY")
print("=" * 80)
print(f"Total log messages: {len(all_logs)}")
print(f"Errors by module:")
for module, count in sorted(error_count.items(), key=lambda x: -x[1]):
    print(f"  {module}: {count}")
print(f"\nWarnings by module:")
for module, count in sorted(warning_count.items(), key=lambda x: -x[1])[:10]:
    print(f"  {module}: {count}")

# Print all errors
print("\n" + "=" * 80)
print("ALL ERRORS FOUND")
print("=" * 80)
errors = [log for log in all_logs if log['level'] == 'ERROR']
for i, err in enumerate(errors[:20], 1):
    print(f"\n{i}. [{err['module']}:{err['lineno']}] {err['logger']}")
    print(f"   {err['message'][:150]}")

if len(errors) > 20:
    print(f"\n... and {len(errors) - 20} more errors (see full_audit.json)")

# Save full results
with open('scripts/full_audit.json', 'w') as f:
    json.dump({
        'summary': {
            'total_logs': len(all_logs),
            'error_count': sum(error_count.values()),
            'warning_count': sum(warning_count.values()),
            'errors_by_module': dict(error_count),
            'warnings_by_module': dict(warning_count),
        },
        'all_errors': [log for log in all_logs if log['level'] == 'ERROR'],
        'all_warnings': [log for log in all_logs if log['level'] == 'WARNING'],
    }, f, indent=2)

print(f"\nFull audit saved to: scripts/full_audit.json")
