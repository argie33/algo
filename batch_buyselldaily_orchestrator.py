#!/usr/bin/env python3
"""
AWS Batch Orchestrator for buyselldaily Loader

Instead of fan-out to 100 Lambda workers, submit a single Batch job
that processes all 5000+ symbols in parallel using EC2 Spot Fleet.

Advantages:
- Single job per run (vs 100 Lambda invocations)
- Spot Fleet saves 60% on compute costs
- Graceful interruption handling with checkpoint persistence
- Better suited for >15min, 4GB memory workloads
- Automatic retry on failure (2 attempts)

Usage:
    aws lambda invoke --function-name BuysellDailyBatchOrchestrator \
      --payload '{"action": "submit"}' \
      /tmp/out.json

    aws lambda invoke --function-name BuysellDailyBatchOrchestrator \
      --payload '{"action": "status", "job_id": "xxxxxxxx-xxxx-xxxx"}' \
      /tmp/out.json
"""

import json
import boto3
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)

batch_client = boto3.client('batch')
logs_client = boto3.client('logs')


def get_all_symbols() -> List[str]:
    """Get all stock symbols from database"""
    import psycopg2

    try:
        secrets_client = boto3.client('secretsmanager')
        secret_name = os.environ.get('RDS_SECRET_ARN', 'stocks-prod-postgres-creds')

        try:
            secret_response = secrets_client.get_secret_value(SecretId=secret_name)
            secret = json.loads(secret_response['SecretString'])
        except Exception:
            secret = {
                'host': os.environ.get('DB_HOST', 'localhost'),
                'port': int(os.environ.get('DB_PORT', '5432')),
                'user': os.environ.get('DB_USER', 'stocks'),
                'password': os.environ.get('DB_PASSWORD', ''),
                'dbname': os.environ.get('DB_NAME', 'stocks')
            }

        conn = None
        cursor = None
        try:
            conn = psycopg2.connect(
                host=secret.get('host'),
                port=secret.get('port', 5432),
                user=secret.get('username', secret.get('user')),
                password=secret.get('password'),
                database=secret.get('dbname', secret.get('name'))
            )

            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
            symbols = [row[0] for row in cursor.fetchall()]

            logger.info(f"Fetched {len(symbols)} active symbols from database")
            return symbols
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    except Exception as e:
        logger.exception(f"Failed to get symbols: {e}")
        raise


def submit_batch_job(symbols: Optional[List[str]] = None) -> Dict:
    """
    Submit a single AWS Batch job for buyselldaily processing.

    Args:
        symbols: Optional list of symbols to process. If None, processes all active symbols.

    Returns:
        Job submission response with job_id
    """
    try:
        # If no symbols provided, fetch all active symbols
        if not symbols:
            symbols = get_all_symbols()

        job_queue = os.environ.get('BATCH_JOB_QUEUE', 'stocks-batch-job-queue-spot')
        job_def = os.environ.get('BATCH_JOB_DEFINITION', 'stocks-buyselldaily')

        # Prepare job container overrides with symbol list
        # For large symbol lists, pass via environment variable (serialized JSON)
        symbols_json = json.dumps(symbols)

        # AWS Batch has env var size limits, so we'll pass symbols count and
        # let the job fetch from database instead
        container_overrides = {
            'environment': [
                {
                    'name': 'SYMBOL_COUNT',
                    'value': str(len(symbols))
                },
                {
                    'name': 'BACKFILL_DAYS',
                    'value': os.environ.get('BACKFILL_DAYS', '30')
                },
                {
                    'name': 'PARALLELISM',
                    'value': os.environ.get('PARALLELISM', '4')
                }
            ]
        }

        response = batch_client.submit_job(
            jobName=f'buyselldaily-{datetime.now().strftime("%Y%m%d-%H%M%S")}',
            jobQueue=job_queue,
            jobDefinition=job_def,
            containerOverrides=container_overrides,
            retryStrategy={
                'attempts': 2  # Retry once if Spot interruption or transient failure
            },
            timeout={
                'attemptDurationSeconds': 1800  # 30 minutes per attempt
            }
        )

        job_id = response['jobId']
        logger.info(f"Submitted Batch job {job_id} for {len(symbols)} symbols")

        return {
            'statusCode': 202,  # Accepted
            'body': json.dumps({
                'job_id': job_id,
                'job_name': response['jobName'],
                'status': 'submitted',
                'symbol_count': len(symbols),
                'timestamp': datetime.now().isoformat()
            })
        }

    except Exception as e:
        logger.exception(f"Failed to submit Batch job: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'status': 'failed'
            })
        }


def get_job_status(job_id: str) -> Dict:
    """Get status of a submitted Batch job"""
    try:
        response = batch_client.describe_jobs(jobs=[job_id])

        if not response['jobs']:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'Job {job_id} not found'})
            }

        job = response['jobs'][0]

        # Get log information if job is running or completed
        logs_info = None
        if job['status'] in ['RUNNING', 'SUCCEEDED', 'FAILED']:
            try:
                log_group = f'/aws/batch/{os.environ.get("PROJECT_NAME", "stocks")}'
                log_stream = f'buyselldaily/{job_id}'

                logs_info = {
                    'log_group': log_group,
                    'log_stream': log_stream,
                    'link': f"https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups/log-group/{log_group}/log-events/{log_stream}"
                }
            except Exception as e:
                logger.warning(f"Could not get logs info: {e}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'job_id': job_id,
                'job_name': job['jobName'],
                'status': job['status'],
                'status_reason': job.get('statusReason', ''),
                'created_at': job['createdAt'],
                'started_at': job.get('startedAt'),
                'stopped_at': job.get('stoppedAt'),
                'attempts': len(job.get('attempts', [])),
                'container': {
                    'image': job['container'].get('image'),
                    'vcpus': job['container'].get('vcpus'),
                    'memory': job['container'].get('memory'),
                    'exit_code': job['container'].get('exitCode')
                },
                'logs': logs_info,
                'timestamp': datetime.now().isoformat()
            })
        }

    except Exception as e:
        logger.exception(f"Failed to get job status: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'status': 'failed'
            })
        }


def list_recent_jobs(limit: int = 10) -> Dict:
    """List recent Batch jobs for buyselldaily"""
    try:
        job_queue = os.environ.get('BATCH_JOB_QUEUE', 'stocks-batch-job-queue-spot')

        # Get jobs in various states
        jobs_by_status = {}
        for status in ['SUBMITTED', 'PENDING', 'RUNNABLE', 'RUNNING', 'SUCCEEDED', 'FAILED']:
            try:
                response = batch_client.list_jobs(
                    jobQueue=job_queue,
                    filters=[
                        {'name': 'job-definition', 'values': ['stocks-buyselldaily']}
                    ],
                    jobStatus=status,
                    maxResults=limit
                )
                jobs_by_status[status] = response['jobSummaryList']
            except Exception as e:
                logger.warning(f"Could not list {status} jobs: {e}")
                jobs_by_status[status] = []

        return {
            'statusCode': 200,
            'body': json.dumps({
                'jobs_by_status': jobs_by_status,
                'timestamp': datetime.now().isoformat()
            }, default=str)
        }

    except Exception as e:
        logger.exception(f"Failed to list jobs: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'status': 'failed'
            })
        }


def lambda_handler(event, context):
    """
    Main Lambda handler for Batch orchestration.

    Event format:
    {
        "action": "submit" | "status" | "list",
        "symbols": ["AAPL", "MSFT"],  # Optional for submit
        "job_id": "xxxxx",  # Required for status
        "limit": 10  # Optional for list
    }
    """
    try:
        action = event.get('action', 'submit')

        if action == 'submit':
            symbols = event.get('symbols')
            return submit_batch_job(symbols)

        elif action == 'status':
            job_id = event.get('job_id')
            if not job_id:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'job_id required for status action'})
                }
            return get_job_status(job_id)

        elif action == 'list':
            limit = event.get('limit', 10)
            return list_recent_jobs(limit)

        else:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': f'Unknown action: {action}',
                    'valid_actions': ['submit', 'status', 'list']
                })
            }

    except Exception as e:
        logger.exception(f"Lambda handler failed: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'status': 'failed'
            })
        }


# For local testing
if __name__ == '__main__':
    import sys

    # Set test environment
    os.environ['BATCH_JOB_QUEUE'] = 'stocks-batch-job-queue-spot'
    os.environ['BATCH_JOB_DEFINITION'] = 'stocks-buyselldaily'
    os.environ['PROJECT_NAME'] = 'stocks'

    # Test event
    test_event = {'action': 'submit'}

    class MockContext:
        def get_remaining_time_in_millis(self):
            return 300000

    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))
