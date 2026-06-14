#!/usr/bin/env python3
"""
Loader Result Logger - Logs ECS task results to database.

FIXED Issue #7: Data Loaders Missing Error Reporting

Triggered by Step Functions after each ECS loader task completes.
Captures success/failure status and error details to data_loader_status table.
"""

import json
import os
import boto3
import logging
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO').upper())

dynamodb = boto3.resource('dynamodb')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        loader_name = event.get('loader_name', 'unknown')
        status = event.get('status', 'UNKNOWN').upper()
        error_type = event.get('error')
        message = event.get('message', '')
        execution_date = event.get('execution_date', datetime.now(timezone.utc).date().isoformat())

        logger.info(f"[LOADER-RESULT] {loader_name}: {status} - {message}")

        # Write to DynamoDB loader status table
        table_name = f"{os.getenv('PROJECT_NAME', 'algo')}-loader-status-{os.getenv('ENVIRONMENT', 'dev')}"

        try:
            table = dynamodb.Table(table_name)

            # Log result with 1-hour TTL
            expires_at = int((datetime.now(timezone.utc).timestamp())) + 3600

            table.put_item(
                Item={
                    'loader_name': loader_name,
                    'execution_date': execution_date,
                    'status': status,
                    'error_type': error_type or 'NONE',
                    'message': message[:500],  # Truncate long messages
                    'task_arn': event.get('task_arn', ''),
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'expires_at': expires_at,
                }
            )

            logger.info(f"[LOADER-RESULT] Logged {loader_name} result to DynamoDB")

        except Exception as db_error:
            logger.error(f"[LOADER-RESULT] Failed to write loader result to DynamoDB: {db_error}")
            raise

        return {
            'statusCode': 200,
            'body': json.dumps({
                'loader': loader_name,
                'status': status,
                'logged': True
            })
        }

    except Exception as e:
        logger.error(f"[LOADER-RESULT] Error processing loader result: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
