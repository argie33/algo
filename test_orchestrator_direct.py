#!/usr/bin/env python3
"""Direct orchestrator test"""
from algo_orchestrator import Orchestrator
from algo_config import get_config
from datetime import date
import logging

logging.basicConfig(level=logging.INFO)

config = get_config()
# Use Friday 2026-05-08 as test date (trading day)
test_date = date(2026, 5, 8)
orch = Orchestrator(config, run_date=test_date, verbose=True)
result = orch.run()

print("\n" + "="*80)
print(f"ORCHESTRATOR EXECUTION COMPLETE")
print("="*80)
print(f"Phases executed: {result.get('phases_executed', 0)}")
print(f"Phases failed: {result.get('phases_failed', 0)}")
print(f"Result: {result}")
