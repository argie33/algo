#!/usr/bin/env python3
"""
Database configuration helper for pattern recognition
"""

import os
import json
import boto3
import logging

logger = logging.getLogger(__name__)

async def get_database_config():
    """Get database configuration from environment or AWS Secrets Manager"""
    
    # Try environment variables first (for local development)
    if all(key in os.environ for key in ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']):
        return {
            'host': os.environ['DB_HOST'],
            'port': int(os.environ['DB_PORT']),
            'database': os.environ['DB_NAME'],
            'user': os.environ['DB_USER'],
            'password': os.environ['DB_PASSWORD']
        }
    
    # Try AWS Secrets Manager
    secret_arn = os.environ.get('DB_SECRET_ARN')
    if secret_arn:
        try:
            client = boto3.client('secretsmanager', 
                                region_name=os.environ.get('AWS_REGION', 'us-east-1'))
            response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response['SecretString'])
            
            return {
                'host': secret['host'],
                'port': secret.get('port', 5432),
                'database': secret['dbname'],
                'user': secret['username'],
                'password': secret['password']
            }
        except Exception as e:
            logger.error(f"Failed to get database credentials from Secrets Manager: {e}")
    
    # Try direct environment endpoint
    db_endpoint = os.environ.get('DB_ENDPOINT')
    if db_endpoint:
        # This is a fallback for Lambda environment
        # You'll need to set the actual credentials
        logger.warning("Using fallback database configuration from environment variables")
        return {
            'host': db_endpoint,
            'port': int(os.environ.get('DB_PORT', 5432)),
            'database': os.environ.get('DB_NAME', 'postgres'),
            'user': os.environ.get('DB_USER', 'postgres'),
            'password': os.environ.get('DB_PASSWORD')
        }
    
    logger.error("No database configuration found")
    return None