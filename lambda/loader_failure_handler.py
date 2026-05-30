#!/usr/bin/env python3

import json
import os
import logging
from datetime import datetime, timezone
import boto3

cloudwatch = boto3.client('cloudwatch')
sns = boto3.client('sns')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Loaders that are CRITICAL - pipeline should alert if they fail
CRITICAL_LOADERS = {
    'stock_prices_daily',
    'stock_symbols',
}

def lambda_handler(event, context):
    """Log loader failure and allow graceful continuation."""
    try:
        loader_name = event.get('loader_name', 'unknown')
        error_type = event.get('error', 'unknown')
        error_message = event.get('error_message', '')
        timestamp = datetime.now(timezone.utc).isoformat()

        # Log the failure
        logger.warning(
            f"Loader failure (graceful degradation): loader={loader_name} "
            f"error={error_type} message={error_message}"
        )

        # Publish CloudWatch metric for visibility (Issue #5)
        cloudwatch.put_metric_data(
            Namespace='Algo/DataLoading',
            MetricData=[
                {
                    'MetricName': 'LoaderFailure',
                    'Value': 1,
                    'Unit': 'Count',
                    'Timestamp': datetime.now(timezone.utc),
                    'Dimensions': [
                        {'Name': 'LoaderName', 'Value': loader_name},
                        {'Name': 'ErrorType', 'Value': error_type},
                    ]
                }
            ]
        )

        # Alert if critical loader failed
        if loader_name in CRITICAL_LOADERS:
            alert_message = (
                f"CRITICAL LOADER FAILURE (Graceful Degradation Active)\n"
                f"Loader: {loader_name}\n"
                f"Error: {error_type}\n"
                f"Message: {error_message}\n"
                f"Time: {timestamp}\n"
                f"\n"
                f"Pipeline is continuing with available data.\n"
                f"This may result in incomplete or stale data."
            )

            sns_topic = os.getenv('SNS_ALERT_TOPIC_ARN')
            if sns_topic:
                try:
                    sns.publish(
                        TopicArn=sns_topic,
                        Subject=f"Critical Loader Failure: {loader_name}",
                        Message=alert_message
                    )
                except Exception as e:
                    logger.error(f"Failed to send SNS alert: {e}")

        # Return success so Step Functions continues (Issue #4 graceful degradation)
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Loader failure logged and pipeline continuing',
                'loader_name': loader_name,
                'timestamp': timestamp,
                'critical': loader_name in CRITICAL_LOADERS
            })
        }

    except Exception as e:
        logger.error(f"Error in loader_failure_handler: {e}", exc_info=True)
        # Even if this handler fails, we return success so pipeline doesn't break
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Handler error - pipeline continuing anyway',
                'error': str(e)
            })
        }
