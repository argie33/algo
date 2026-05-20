"""
Simplified Lambda handler - runs algo orchestrator directly without subprocesses.
Avoids psycopg2 import issues by keeping database operations local.
"""

import os
import sys
import json
import logging
from datetime import datetime, date as _date

# DEBUG: Log Python path and available modules before importing config
sys.stderr.write(f"\n=== LAMBDA DEBUG ===\nPython path: {sys.path}\n")
import pkgutil
sys.stderr.write(f"Available top-level packages: {[name for finder, name, ispkg in pkgutil.iter_modules(sys.path)]}\n")
sys.stderr.write(f"Current working directory: {os.getcwd()}\n")
sys.stderr.write(f"Lambda task root: {os.getenv('LAMBDA_TASK_ROOT', 'not set')}\n")
sys.stderr.write(f"Import path check - config exists?: {os.path.exists('/var/task/config')}\n")
sys.stderr.write("=== END DEBUG ===\n\n")

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
    execution_id = getattr(context, 'aws_request_id', 'manual') if context else 'local'
    start_time = datetime.utcnow()

    try:
        logger.info("=" * 80)
        logger.info(f"Algo Orchestrator Starting (Execution ID: {execution_id})")
        logger.info(f"Execution Mode: {EXECUTION_MODE}")
        logger.info(f"Dry Run: {DRY_RUN}")
        logger.info("=" * 80)

        # Prepare database credentials (from Secrets Manager or env vars)
        prepare_database_credentials()

        # Import and run orchestrator directly (no subprocess)
        # Import from the root-level algo_orchestrator.py module, not the package
        from algo.algo_orchestrator import Orchestrator

        orchestrator = Orchestrator(
            run_date=None,
            dry_run=DRY_RUN,
            verbose=True
        )

        final_result = orchestrator.run()

        elapsed = (datetime.utcnow() - start_time).total_seconds()

        logger.info("=" * 80)
        logger.info(f"✅ Execution completed successfully ({elapsed:.1f}s)")
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
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        error_msg = f"Execution failed after {elapsed:.1f}s: {str(e)}"

        logger.error("=" * 80)
        logger.error(f"❌ {error_msg}")
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
