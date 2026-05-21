"""
Lambda handler for algo orchestrator.

Uses Lambda Layers for config/, algo/, utils/ code which are extracted to /opt/python.
This is more reliable than bundling everything in the function ZIP.
"""

import os
import sys
import json
import logging
from datetime import datetime, date as _date

# Lambda Layers automatically add /opt/python to sys.path
# config/, algo/, utils/ will be found there
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

logger.info("Lambda runtime version: Python 3.11")
logger.info(f"sys.path includes {len(sys.path)} paths")

from config.credential_helper import get_db_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXECUTION_MODE = os.getenv('EXECUTION_MODE', 'paper')
DRY_RUN = os.getenv('ORCHESTRATOR_DRY_RUN', 'false').lower() == 'true'

def prepare_database_credentials():
    """Prepare database credentials for Lambda execution.

    In AWS Lambda, credentials come from Secrets Manager via DATABASE_SECRET_ARN.
    This function ensures they're available for the orchestrator.
    credential_helper.get_db_config() will handle the fallback logic.
    """
    try:
        # If DATABASE_SECRET_ARN is set, credential_manager will use it
        # If DB_PASSWORD env var is set, credential_helper will use it
        # Either way, we're good — just validate the connection can be made
        cfg = get_db_config()
        logger.info(f"Database configuration ready: {cfg['host']}:{cfg['port']}/{cfg['database']}")
    except Exception as e:
        logger.error(f"Failed to prepare database credentials: {str(e)}")
        raise

def lambda_handler(event, context):
    """
    Simplified handler - runs algo_orchestrator directly.
    """
    print("[HANDLER ENTRY] Lambda handler called")  # Explicit stdout for debugging
    execution_id = getattr(context, 'aws_request_id', 'manual') if context else 'local'
    start_time = datetime.utcnow()

    try:
        logger.info("=" * 80)
        logger.info(f"Algo Orchestrator Starting (Execution ID: {execution_id})")
        logger.info(f"Execution Mode: {EXECUTION_MODE}")
        logger.info(f"Dry Run: {DRY_RUN}")
        logger.info("=" * 80)
        print("[HANDLER] Logger initialized, starting main flow")  # Debug output

        # Prepare database credentials (from Secrets Manager or env vars)
        print("[HANDLER] About to prepare database credentials")
        logger.info("[DEBUG] Preparing database credentials...")
        prepare_database_credentials()
        logger.info("[DEBUG] Database credentials prepared OK")
        print("[HANDLER] Database credentials prepared")

        # Import and run orchestrator directly (no subprocess)
        # Import from the root-level algo_orchestrator.py module, not the package
        print("[HANDLER] About to import Orchestrator class")
        logger.info("[DEBUG] Importing Orchestrator class...")
        from algo.algo_orchestrator import Orchestrator
        logger.info("[DEBUG] Orchestrator class imported successfully")
        print("[HANDLER] Orchestrator class imported")
        print(f"[HANDLER] DRY_RUN={DRY_RUN}, EXECUTION_MODE={EXECUTION_MODE}")

        print("[HANDLER] About to create Orchestrator instance")
        logger.info("[DEBUG] Creating Orchestrator instance...")
        orchestrator = Orchestrator(
            run_date=None,
            dry_run=DRY_RUN,
            verbose=True
        )
        print("[HANDLER] Orchestrator instance created successfully")
        logger.info("[DEBUG] Orchestrator instance created successfully")

        print("[HANDLER] About to call orchestrator.run()")
        logger.info("[DEBUG] Calling orchestrator.run()...")
        final_result = orchestrator.run()
        print(f"[HANDLER] orchestrator.run() completed with result: {final_result}")
        logger.info(f"[DEBUG] orchestrator.run() completed with result: {final_result}")

        elapsed = (datetime.utcnow() - start_time).total_seconds()

        logger.info("=" * 80)
        logger.info(f"✅ Execution completed successfully ({elapsed:.1f}s)")
        logger.info(f"Final result: {final_result}")
        logger.info("=" * 80)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'execution_id': execution_id,
                'elapsed_seconds': elapsed,
                'execution_mode': EXECUTION_MODE,
                'dry_run': DRY_RUN,
                'timestamp': start_time.isoformat(),
            })
        }

    except Exception as e:
        import traceback
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        error_msg = f"Execution failed after {elapsed:.1f}s: {str(e)}"

        print(f"[ERROR] Exception caught: {str(e)}")
        print("[ERROR] Full traceback:")
        print(traceback.format_exc())

        logger.error("=" * 80)
        logger.error(f"❌ {error_msg}")
        logger.error(traceback.format_exc())
        logger.error("=" * 80)

        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'execution_id': execution_id,
                'error': str(e),
                'elapsed_seconds': elapsed,
                'timestamp': start_time.isoformat(),
            })
        }
