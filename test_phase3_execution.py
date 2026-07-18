#!/usr/bin/env python3
"""Debug script to test Phase 3 execution."""

import logging
import sys
from datetime import date as _date

from algo.config.environment_validation import EnvironmentValidator
from algo.infrastructure import get_config
from algo.orchestration import Orchestrator
from algo.orchestrator.phase_registry import PhaseRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validate environment
EnvironmentValidator.require_valid_or_halt("test_phase3")

# Get config
config = get_config()
logger.info(f"Config loaded: execution_mode={config.get('execution_mode')}")

# Check Phase Registry
logger.info("\n=== PHASE REGISTRY ===")
for phase in PhaseRegistry.get_all_phases():
    logger.info(f"Phase {phase.phase_num}: {phase.phase_name}")
    logger.info(f"  Dependencies: {phase.dependencies}")
    logger.info(f"  Skip if halted: {phase.skip_if_halted}")
    logger.info(f"  Always run: {phase.always_run}")

# Try to create and set up executor
logger.info("\n=== EXECUTOR SETUP ===")
orchestrator = Orchestrator(config=config, run_date=_date.today(), dry_run=True, verbose=True)

# Setup executor
executor = orchestrator._setup_executor(skip_phases=None)
logger.info(f"Executor phases registered: {list(executor.phases.keys())}")
logger.info(f"Execution order: {executor.execution_order}")

# Check Phase 3 specifically
if 3 in executor.phases:
    phase3 = executor.phases[3]
    logger.info(f"\nPhase 3 details:")
    logger.info(f"  Name: {phase3.phase_name}")
    logger.info(f"  Dependencies: {phase3.dependencies}")
    logger.info(f"  Skip if halted: {phase3.skip_if_halted}")
    logger.info(f"  Always run: {phase3.always_run}")
    logger.info(f"  Execute fn set: {phase3.execute_fn is not None}")
else:
    logger.error("Phase 3 NOT found in executor.phases!")

logger.info("\n=== VALIDATION ===")
errors = executor.validate()
if errors:
    logger.error(f"Validation errors: {errors}")
else:
    logger.info("Executor validation passed")

logger.info("\nPhase 3 execution test complete")
