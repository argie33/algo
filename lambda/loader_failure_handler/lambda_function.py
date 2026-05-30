"""
Loader Failure Handler Lambda

Handles errors from data loaders in the Step Functions EOD pipeline.
Logs failures to CloudWatch and optionally sends SNS alerts.
"""

import json
import boto3
import os
from datetime import datetime

cloudwatch = boto3.client('cloudwatch')
sns = boto3.client('sns')


def lambda_handler(event, context):
    """
    Handle loader failures from Step Functions pipeline.

    Args:
        event: Step Functions execution event with:
            - loader_name: Name of failed loader
            - error: Error code/type
            - error_message: Error message/details
        context: Lambda context

    Returns:
        Dict with:
            - statusCode: 200 for success, 4xx/5xx for errors
            - body: JSON response
    """
    try:
        loader_name = event.get('loader_name', 'unknown')
        error = event.get('error', 'Unknown')
        error_message = event.get('error_message', 'No error details')

        # Log to CloudWatch
        print(f"Loader Failure: {loader_name}")
        print(f"  Error: {error}")
        print(f"  Message: {error_message}")

        # Emit metric to CloudWatch
        cloudwatch.put_metric_data(
            Namespace='Algo/DataLoading',
            MetricData=[
                {
                    'MetricName': 'LoaderFailure',
                    'Value': 1,
                    'Unit': 'Count',
                    'Dimensions': [
                        {'Name': 'LoaderName', 'Value': loader_name}
                    ],
                    'Timestamp': datetime.utcnow()
                }
            ]
        )

        # Send SNS alert if configured
        sns_topic = os.getenv('SNS_ALERTS_TOPIC_ARN')
        if sns_topic:
            sns.publish(
                TopicArn=sns_topic,
                Subject=f'Data Loader Failure: {loader_name}',
                Message=f"""
Loader: {loader_name}
Error: {error}
Details: {error_message}
Time: {datetime.utcnow().isoformat()}
""".strip()
            )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Failure logged',
                'loader_name': loader_name,
                'error': error
            })
        }

    except Exception as e:
        print(f"Error in failure handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
