#!/usr/bin/env python3
import os
os.environ["LOCAL_MODE"] = "true"

from utils.dotenv_loader import load_env_local
load_env_local()

from algo.orchestration.orchestrator import Orchestrator
from algo.infrastructure.config import AlgoConfig
from datetime import date

print("\n" + "="*80)
print("VERIFICATION RUN - ALL FIXES")
print("="*80)

try:
    config = AlgoConfig()
    orch = Orchestrator(config, run_date=date.today(), dry_run=True, verbose=False)
    result = orch.run()

    # Check results
    print("\nPHASE RESULTS:")
    for phase in result['phases']:
        status_icon = "✅" if phase['status'] == 'ok' else "⚠️ " if phase['status'] in ['degraded', 'blocked'] else "❌"
        print(f"  {status_icon} Phase {phase['phase']}: {phase['name']:30} [{phase['status']:10}]")

    if result['success']:
        print(f"\n✅ ORCHESTRATOR RUN SUCCESSFUL - {result['halted']=}, {result['skipped']=}")
    else:
        print(f"\n❌ ORCHESTRATOR RUN FAILED - {result}")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
