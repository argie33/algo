#!/usr/bin/env python3
"""
Run orchestrator with automatic credential loading from database.

This wrapper:
1. Loads Alpaca credentials from database (algo_config)
2. Sets them as environment variables
3. Runs the orchestrator

Usage:
    python scripts/run_orchestrator_with_creds.py --morning
    python scripts/run_orchestrator_with_creds.py --afternoon
    python scripts/run_orchestrator_with_creds.py --evening
    python scripts/run_orchestrator_with_creds.py --run-all
"""

import os
import subprocess
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

from scripts.load_credentials import ensure_credentials_loaded

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='[%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Load credentials and run orchestrator."""
    # Load Alpaca credentials from database
    try:
        logger.info('[WRAPPER] Loading Alpaca credentials from database...')
        ensure_credentials_loaded()
        logger.info('[WRAPPER] Credentials loaded successfully')
    except Exception as e:
        logger.error(f'[WRAPPER] Failed to load credentials: {e}')
        sys.exit(1)

    # Run orchestrator with provided arguments
    logger.info(f'[WRAPPER] Running orchestrator with args: {sys.argv[1:]}')

    try:
        result = subprocess.run(
            [sys.executable, 'scripts/run_local_orchestrator.py', *sys.argv[1:]],
            cwd=str(project_root),
        )
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        logger.info('[WRAPPER] Orchestrator interrupted by user')
        sys.exit(0)
    except Exception as e:
        logger.error(f'[WRAPPER] Failed to run orchestrator: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
