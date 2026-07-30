#!/usr/bin/env python3
import os
os.environ["LOCAL_MODE"] = "true"

from utils.dotenv_loader import load_env_local
load_env_local()

from algo.orchestration.orchestrator import Orchestrator
from algo.infrastructure.config import AlgoConfig
from datetime import date

config = AlgoConfig()
orch = Orchestrator(config, run_date=date.today(), dry_run=True, verbose=False)
result = orch.run()

# Show summary
print("\n" + "="*80)
print("ORCHESTRATOR RUN SUMMARY")
print("="*80)
for phase in result['phases']:
    phase_num = phase['phase']
    name = phase['name']
    status = phase['status']
    summary = phase['summary']
    print(f"Phase {phase_num}: {name:30} [{status:10}] {summary[:60]}")
print("="*80)
