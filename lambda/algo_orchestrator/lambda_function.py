#!/usr/bin/env python3
"""
Lambda handler for the Algo Orchestrator.

Wraps the 7-phase orchestrator in a Lambda-compatible handler.
Supports both scheduled execution (EventBridge) and manual invocation (test-orchestrator.yml).
"""

import json
import os
import sys
import logging
from pathlib import Path
from datetime import date as _date

# Setup logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Add project root to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the orchestrator
from algo.algo_orchestrator import Orchestrator
from config.credential_helper import load_env


def lambda_handler(event, context):
    """
    Lambda entry point for Algo Orchestrator.

    Event payload (optional):
    {
        "source": "test-live-execution",
        "test": "true",
        "timeout": 120,
        "dry_run": false,
        "skip_freshness": false,
        "date": "2026-05-23"
    }

    Returns:
        {
            "statusCode": 200 | 500,
            "body": {
                "status": "success" | "error",
                "message": "...",
                "run_id": "...",
                "phases": {...},
                "source": "..."
            }
        }
    """
    source = "unknown"
    try:
        # Load environment variables
        load_env()

        # Parse event payload
        source = event.get('source', 'eventbridge')
        is_test = event.get('test', False)
        dry_run = event.get('dry_run', False)
        skip_freshness = event.get('skip_freshness', False)
        run_date_str = event.get('date', None)

        logger.info(f"Orchestrator invoked: source={source}, is_test={is_test}, dry_run={dry_run}")

        # Get timeout from Lambda context (in seconds)
        lambda_timeout = context.get_remaining_time_in_millis() // 1000 if context else 240

        # Parse run date if provided
        run_date = None
        if run_date_str:
            try:
                run_date = _date.fromisoformat(run_date_str)
            except (ValueError, TypeError):
                logger.warning(f"Invalid date format: {run_date_str}, using today")

        # Create orchestrator instance
        orchestrator = Orchestrator(
            run_date=run_date,
            dry_run=dry_run,
            verbose=not is_test,
        )

        # Apply additional options
        if skip_freshness:
            orchestrator.skip_freshness = True
            logger.warning("WARNING: skip_freshness set. Data may be stale.")

        # Run the orchestrator
        logger.info(f"Starting orchestrator run")
        try:
            result = orchestrator.run()
            success = result.get('success', False)
            run_id = result.get('run_id', 'unknown')

            # Return response
            return {
                'statusCode': 200 if success else 500,
                'body': json.dumps({
                    'status': 'success' if success else 'error',
                    'message': 'Orchestrator completed successfully' if success else 'Orchestrator encountered errors',
                    'run_id': run_id,
                    'phases': result.get('phases', {}),
                    'source': source,
                    'lambda_timeout_seconds': lambda_timeout,
                })
            }
        finally:
            orchestrator.cleanup()

    except Exception as e:
        logger.exception(f"Orchestrator Lambda handler error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'message': f'Orchestrator failed: {str(e)}',
                'source': source,
            })
        }
