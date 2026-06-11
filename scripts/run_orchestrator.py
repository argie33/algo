#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path

# Set environment for testing
os.environ['BYPASS_PHASE1_HALT'] = 'true'
os.environ['BYPASS_HALT_FLAG'] = 'true'
os.environ['BYPASS_CIRCUIT_BREAKERS'] = 'true'
os.environ['BYPASS_MARKET_REGIME'] = 'true'
os.environ['BYPASS_EXPOSURE_POLICY'] = 'true'

sys.path.insert(0, str(Path(__file__).parent))

from algo.algo_orchestrator import Orchestrator

print("="*80)
print("ORCHESTRATOR RUN WITH CURRENT DATA")
print("="*80)
print()
print("Bypass flags: ALL ENABLED")
print()

try:
    orch = Orchestrator(dry_run=False, verbose=True)
    result = orch.run()
    
    print()
    print("="*80)
    print("RESULTS")
    print("="*80)
    print("Status: {}".format("SUCCESS" if result.get('success') else "INCOMPLETE"))
    print("Run ID: {}".format(result.get('run_id')))
    print()
    
    phases = result.get('phases', {})
    print("Phases executed:")
    for pnum in sorted(phases.keys(), key=int):
        p = phases[pnum]
        status = p.get('status', 'unknown').upper()
        summary = p.get('summary', '')
        print()
        print("Phase {}: {} ({})".format(pnum, p.get('name', 'unknown').upper(), status))
        if summary:
            print("  Summary: {}".format(summary))
        if p.get('halted'):
            print("  HALTED")
    
    print()
    print("="*80)
    
except Exception as e:
    print("ERROR: {}".format(e))
    import traceback
    traceback.print_exc()
