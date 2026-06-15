#!/usr/bin/env python3
import logging
from datetime import date
from algo.algo_orchestrator import Orchestrator
from algo.infrastructure import get_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("__main__")

try:
    logger.info("Starting orchestrator in dry-run mode...")
    config = get_config()
    orch = Orchestrator(
        config=config, run_date=date.today(), dry_run=True, verbose=True
    )
    result = orch.run()

    if result.get("success"):
        logger.info(f"SUCCESS: {result}")
    else:
        logger.critical(f"FAILED: {result}")
        if result.get("reason"):
            logger.critical(f"Reason: {result['reason']}")
except Exception as e:
    logger.exception(f"Error running orchestrator: {e}")
