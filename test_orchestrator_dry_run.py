#!/usr/bin/env python3
"""Direct orchestrator test in dry-run mode to find real issues."""

import sys
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

# Setup path and credentials
from utils.dotenv_loader import load_env_local
load_env_local()

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from scripts.load_credentials import ensure_credentials_loaded
    ensure_credentials_loaded()
except Exception as e:
    logging.getLogger(__name__).warning(f"[CREDS] Could not load credentials: {e}")

# Now import and run orchestrator
from algo.infrastructure.config.main import AlgoConfig
from algo.orchestration.orchestrator import Orchestrator

print("\n" + "="*70)
print("ORCHESTRATOR DRY-RUN TEST")
print("="*70)

try:
    # Load config
    config = AlgoConfig()
    execution_mode = config.get("execution_mode", "unknown")
    print(f"[OK] Config loaded (execution_mode={execution_mode})")

    # Run orchestrator in dry-run mode
    print(f"\nRunning orchestrator in dry-run mode...")
    orch = Orchestrator(config=config, dry_run=True, verbose=True)
    result = orch.run()

    print("\n" + "="*70)
    print("ORCHESTRATOR COMPLETED SUCCESSFULLY")
    print("="*70)
    print(f"Result: {result}")

except Exception as e:
    print(f"\n[CRITICAL ERROR] {type(e).__name__}")
    print(f"Message: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
