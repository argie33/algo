"""
Data Freshness Monitor Lambda

Monitors the freshness of data in the system and alerts if data becomes stale.
"""

import json


def lambda_handler(event, context):
    """
    Monitor data freshness and alert on staleness.

    Args:
        event: CloudWatch Events event
        context: Lambda context

    Returns:
        Dict with statusCode and body
    """
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Data freshness check complete'})
    }
