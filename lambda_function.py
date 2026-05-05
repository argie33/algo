"""
Simplified Lambda handler - runs algo orchestrator directly without subprocesses.
Avoids psycopg2 import issues by keeping database operations local.
"""

import json
import os
import sys
import logging
from datetime import datetime, date as _date

# Add repo root to path so we can import algo modules
sys.path.insert(0, '/var/task')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXECUTION_MODE = os.getenv('EXECUTION_MODE', 'paper')
DRY_RUN = os.getenv('DRY_RUN_MODE', 'true').lower() == 'true'

def get_database_credentials():
    """Fetch database credentials from AWS Secrets Manager."""
    try:
        import boto3
        secrets = boto3.client('secretsmanager')
        secret_arn = os.getenv('DATABASE_SECRET_ARN')
        if not secret_arn:
            raise ValueError('DATABASE_SECRET_ARN environment variable not set')

        response = secrets.get_secret_value(SecretId=secret_arn)
        creds = json.loads(response['SecretString'])

        os.environ['DB_HOST'] = creds.get('host', 'localhost')
        os.environ['DB_PORT'] = str(creds.get('port', 5432))
        os.environ['DB_USER'] = creds.get('username', 'stocks')
        os.environ['DB_PASSWORD'] = creds.get('password', '')
        os.environ['DB_NAME'] = creds.get('dbname', 'stocks')

        logger.info("Database credentials loaded from Secrets Manager")
    except Exception as e:
        logger.error(f"Failed to get database credentials: {str(e)}")
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

        # Fetch database credentials from Secrets Manager
        get_database_credentials()

        # Import and run orchestrator directly (no subprocess)
        from algo_orchestrator import Orchestrator

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
