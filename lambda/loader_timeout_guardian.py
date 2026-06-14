#!/usr/bin/env python3
"""
CloudWatch Lambda: Monitor and kill loaders stuck in RUNNING state.

Runs every 5 minutes via EventBridge. Kills ECS tasks and updates DB
if a loader has been RUNNING for longer than allowed.

MAX DURATIONS (HARD LIMITS):
- Price loaders: 4 hours (yfinance can be slow)
- Technical/score loaders: 2 hours
- Other loaders: 1 hour
"""

import boto3
import logging
from datetime import datetime, timedelta, timezone
import os
import psycopg2
from dateutil.parser import parse as parse_datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ecs = boto3.client('ecs')
cloudwatch = boto3.client('cloudwatch')

# Maximum allowed runtime before killing
MAX_RUNTIME_SECONDS = {
    'stock_prices_daily': 4 * 3600,  # 4 hours max
    'etf_price_daily': 4 * 3600,
    'technical_data_daily': 2 * 3600,  # 2 hours max
    'swing_trader_scores': 2 * 3600,
    'signal_quality_scores': 2 * 3600,
    'buy_sell_daily': 2 * 3600,
    # Default for all others
    'DEFAULT': 1 * 3600  # 1 hour max
}

def get_max_runtime(loader_name):
    return MAX_RUNTIME_SECONDS.get(loader_name, MAX_RUNTIME_SECONDS['DEFAULT'])

def lambda_handler(event, context):
    """Monitor and kill indefinitely-running loaders."""
    try:
        # Connect to database
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT', 5432)),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME')
        )

        with conn.cursor() as cur:
            # Find loaders in RUNNING state
            cur.execute('''
                SELECT table_name, execution_started
                FROM data_loader_status
                WHERE status = 'RUNNING' AND execution_started IS NOT NULL
            ''')

            hung_loaders = []
            now = datetime.now(timezone.utc)

            for loader_name, started in cur.fetchall():
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)

                runtime_sec = (now - started).total_seconds()
                max_allowed = get_max_runtime(loader_name)

                if runtime_sec > max_allowed:
                    hung_loaders.append({
                        'name': loader_name,
                        'runtime_sec': runtime_sec,
                        'max_allowed': max_allowed
                    })

            if hung_loaders:
                logger.warning(f'Found {len(hung_loaders)} indefinitely-running loaders:')
                for loader in hung_loaders:
                    logger.warning(
                        f'  {loader["name"]}: running {loader["runtime_sec"]/3600:.1f}h '
                        f'(max {loader["max_allowed"]/3600:.1f}h)'
                    )

                    # Kill the ECS task
                    kill_loader_task(loader['name'])

                    # Mark as TIMEOUT in database
                    cur.execute('''
                        UPDATE data_loader_status
                        SET status = 'TIMEOUT',
                            error_message = 'Killed by timeout guardian after ' ||
                                            ROUND(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - execution_started))/3600) || 'h',
                            execution_completed = CURRENT_TIMESTAMP
                        WHERE table_name = %s AND status = 'RUNNING'
                    ''', (loader['name'],))

                    # Alert via CloudWatch
                    cloudwatch.put_metric_data(
                        Namespace='AlgoLoaders',
                        MetricData=[{
                            'MetricName': 'LoaderTimeout',
                            'Value': 1,
                            'Unit': 'Count',
                            'Dimensions': [{'Name': 'LoaderName', 'Value': loader['name']}]
                        }]
                    )

            conn.commit()
            conn.close()

            return {
                'statusCode': 200,
                'body': f'Checked loaders. Found {len(hung_loaders)} hung (killed and logged)'
            }

    except Exception as e:
        logger.error(f'Guardian check failed: {e}', exc_info=True)
        return {'statusCode': 500, 'body': str(e)}

def kill_loader_task(loader_name):
    """Find and kill ECS task running this loader."""
    try:
        # List tasks in algo cluster
        response = ecs.list_tasks(cluster='algo-dev', desiredStatus='RUNNING')
        task_arns = response.get('taskArns', [])

        # Try to match by task name/label - this is heuristic
        # In real deployment, tasks should have loader_name as label or environment variable
        for arn in task_arns:
            try:
                task_detail = ecs.describe_tasks(cluster='algo-dev', tasks=[arn])
                task = task_detail['tasks'][0]

                # Check task definition or environment variables for loader_name
                # This depends on how tasks are launched
                container_env = task['containers'][0].get('environment', [])
                for env_var in container_env:
                    if env_var.get('name') == 'LOADER_NAME' and env_var.get('value') == loader_name:
                        # Found it - stop the task
                        ecs.stop_task(
                            cluster='algo-dev',
                            task=arn,
                            reason=f'Killed by timeout guardian: {loader_name} exceeded max runtime'
                        )
                        logger.info(f'Stopped ECS task {arn.split("/")[-1]}')
                        return True
            except Exception as e:
                logger.warning(f'Could not check task {arn}: {e}')

        logger.warning(f'Could not find ECS task for {loader_name}')
        return False

    except Exception as e:
        logger.error(f'Failed to kill task for {loader_name}: {e}')
        return False
