#!/usr/bin/env python3
"""Entrypoint for data patrol ECS task.

ECS task definition runs: python3 algo/algo_data_patrol.py
Implementation lives in: algo/monitoring/data_patrol/ (modular architecture)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from algo.monitoring.data_patrol import DataPatrol
from utils.infrastructure.timeout import ExecutionTimeout, ExecutionTimeoutError

root = Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        with ExecutionTimeout(max_seconds=600, label="data_patrol"):
            parser = argparse.ArgumentParser(description="Data integrity patrol")
            parser.add_argument("--quick", action="store_true", help="Critical checks only")
            parser.add_argument(
                "--validate-alpaca",
                action="store_true",
                help="Cross-validate vs Alpaca",
            )
            parser.add_argument("--json", action="store_true", help="JSON output")
            args = parser.parse_args()

            p = DataPatrol()
            summary = p.run(quick=args.quick, validate_alpaca=args.validate_alpaca)

            if args.json:
                logger.info(json.dumps(summary, default=str, indent=2))

            sys.exit(0 if summary["ready"] else 1)
    except (ExecutionTimeoutError, KeyError, ValueError, RuntimeError) as e:
        logger.error(f"Data patrol execution failed: {e}", exc_info=True)
        sys.exit(1)
