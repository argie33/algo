#!/usr/bin/env python3
"""
Lambda Results Aggregator for Step Functions Massive Parallel Processing

Invoked after the Map state completes, this function aggregates results from
1000+ parallel symbol processing jobs and provides summary statistics.

Input from Step Functions Map state:
[
  {
    "symbol": "AAPL",
    "status": "success",
    "rows_inserted": 150,
    "duration_ms": 1234
  },
  {
    "symbol": "MSFT",
    "status": "error",
    "error": "Price data not available",
    "duration_ms": 500
  },
  ...
]

Output:
{
  "status": "completed",
  "total_symbols": 5000,
  "symbols_processed": 4987,
  "symbols_failed": 13,
  "total_rows_inserted": 750000,
  "average_duration_ms": 1234,
  "total_duration_ms": 6175000,
  "errors": [
    {
      "symbol": "UNKNOWN",
      "error": "Price data not available"
    },
    ...
  ]
}
"""

import json
import logging
import os
import time
from collections import defaultdict
from typing import Dict, List, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def aggregate_results(results: List[Dict]) -> Dict[str, Any]:
    """
    Aggregate results from Map state execution.

    Args:
        results: List of results from individual symbol processing

    Returns:
        Aggregated statistics
    """
    if not results:
        return {
            'status': 'empty',
            'total_symbols': 0,
            'symbols_processed': 0,
            'symbols_failed': 0,
            'total_rows_inserted': 0,
            'average_duration_ms': 0
        }

    total_symbols = len(results)
    symbols_processed = 0
    symbols_failed = 0
    total_rows_inserted = 0
    total_duration_ms = 0
    durations = []
    errors = []
    status_counts = defaultdict(int)

    for result in results:
        symbol = result.get('symbol', 'unknown')
        status = result.get('status', 'unknown')
        status_counts[status] += 1

        if status == 'success':
            symbols_processed += 1
            rows = result.get('rows_inserted', 0)
            total_rows_inserted += rows

        elif status in ['error', 'no_data', 'no_signals']:
            symbols_failed += 1
            error_msg = result.get('error', f'Status: {status}')
            errors.append({
                'symbol': symbol,
                'status': status,
                'error': error_msg
            })

        duration = result.get('duration_ms', 0)
        if duration > 0:
            durations.append(duration)
            total_duration_ms += duration

    average_duration = sum(durations) / len(durations) if durations else 0
    min_duration = min(durations) if durations else 0
    max_duration = max(durations) if durations else 0

    return {
        'status': 'completed',
        'total_symbols': total_symbols,
        'symbols_processed': symbols_processed,
        'symbols_failed': symbols_failed,
        'symbols_with_no_data': status_counts.get('no_data', 0),
        'symbols_with_no_signals': status_counts.get('no_signals', 0),
        'total_rows_inserted': total_rows_inserted,
        'average_duration_ms': round(average_duration, 2),
        'min_duration_ms': min_duration,
        'max_duration_ms': max_duration,
        'total_duration_ms': total_duration_ms,
        'errors': errors[:100],  # Return first 100 errors to avoid payload size limits
        'error_count': len(errors),
        'status_breakdown': dict(status_counts)
    }


def save_aggregated_results(conn, aggregated: Dict) -> bool:
    """
    Save aggregated execution results to database for audit trail.

    Args:
        conn: Database connection
        aggregated: Aggregated results dictionary

    Returns:
        True if successful
    """
    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO execution_history
            (execution_type, total_symbols, symbols_processed, symbols_failed,
             total_rows_inserted, average_duration_ms, total_duration_ms,
             error_count, execution_date, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            """,
            (
                'massive_parallel_signals',
                aggregated['total_symbols'],
                aggregated['symbols_processed'],
                aggregated['symbols_failed'],
                aggregated['total_rows_inserted'],
                aggregated['average_duration_ms'],
                aggregated['total_duration_ms'],
                aggregated['error_count']
            )
        )

        # Also save individual error details if there were errors
        if aggregated.get('errors'):
            for error_detail in aggregated['errors']:
                cur.execute(
                    """
                    INSERT INTO execution_errors
                    (execution_type, symbol, error_message, error_date, created_at)
                    VALUES (%s, %s, %s, NOW(), NOW())
                    """,
                    (
                        'massive_parallel_signals',
                        error_detail['symbol'],
                        error_detail['error']
                    )
                )

        conn.commit()
        cur.close()
        logger.info(f"Saved aggregated results to database")
        return True

    except Exception as e:
        logger.exception(f"Failed to save aggregated results: {e}")
        if conn:
            conn.rollback()
        return False


def get_db_connection():
    """Get RDS database connection"""
    import boto3
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

        conn = psycopg2.connect(
            host=secret.get('host'),
            port=secret.get('port', 5432),
            user=secret.get('username', secret.get('user')),
            password=secret.get('password'),
            database=secret.get('dbname', secret.get('name'))
        )
        return conn
    except Exception as e:
        logger.exception(f"Failed to connect to database: {e}")
        raise


def lambda_handler(event, context) -> Dict:
    """
    Lambda handler for aggregating Step Functions Map state results.

    Input: Array of symbol processing results
    Output: Aggregated statistics

    Event structure:
    {
      "Payload": [
        {
          "symbol": "AAPL",
          "status": "success",
          "rows_inserted": 150,
          "duration_ms": 1234
        },
        ...
      ]
    }
    """
    start_time = time.time()

    try:
        # Extract results from Step Functions Payload
        results = event.get('Payload', [])

        if not results:
            logger.warning("No results received from Map state")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'status': 'error',
                    'error': 'No results received from Map state'
                })
            }

        logger.info(f"Aggregating results from {len(results)} symbol processes")

        # Aggregate results
        aggregated = aggregate_results(results)

        # Try to save to database (non-blocking - don't fail if DB fails)
        try:
            conn = get_db_connection()
            try:
                save_aggregated_results(conn, aggregated)
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Could not save results to database: {e} (continuing anyway)")

        # Add execution metadata
        aggregated['execution_duration_ms'] = int((time.time() - start_time) * 1000)
        aggregated['timestamp'] = time.time()

        logger.info(f"Aggregation complete: {aggregated['symbols_processed']} symbols processed, "
                   f"{aggregated['symbols_failed']} failed, "
                   f"{aggregated['total_rows_inserted']} rows inserted")

        return {
            'statusCode': 200,
            'body': json.dumps(aggregated)
        }

    except Exception as e:
        logger.exception(f"Failed to aggregate results: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'error': str(e)
            })
        }


# For local testing
if __name__ == "__main__":
    test_results = [
        {
            "symbol": "AAPL",
            "status": "success",
            "rows_inserted": 150,
            "duration_ms": 1234
        },
        {
            "symbol": "MSFT",
            "status": "success",
            "rows_inserted": 200,
            "duration_ms": 1500
        },
        {
            "symbol": "UNKNOWN",
            "status": "error",
            "error": "Price data not available",
            "duration_ms": 100
        }
    ]

    test_event = {
        "Payload": test_results
    }

    class MockContext:
        pass

    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))
