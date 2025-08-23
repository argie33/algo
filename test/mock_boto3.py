"""
Mock AWS boto3 module for testing.
This module intercepts AWS calls and provides mock responses.
"""

import json
import logging
import os
from unittest.mock import MagicMock

logger = logging.getLogger("mock_boto3")

# Mock database credentials for testing
# Use localhost for local testing, postgres for Docker
DB_HOST = os.environ.get("TEST_DB_HOST", "localhost")  # Allow override via environment
MOCK_DB_SECRET = {
    "host": DB_HOST,
    "port": "5432",
    "username": "postgres",  # Default postgres user
    "password": "testpass",
    "dbname": "postgres",  # Default postgres database
}


class MockSecretsManagerClient:
    """Mock AWS Secrets Manager client"""

    def __init__(self, **kwargs):
        logger.info("Created mock Secrets Manager client")

    def get_secret_value(self, SecretId):
        """Mock get_secret_value method"""
        logger.info(f"Mock: Getting secret value for SecretId: {SecretId}")
        # Accept both 'mock' and 'test-db-secret' for test convenience
        if SecretId in ("mock", "test-db-secret"):
            response = {
                "SecretString": json.dumps(MOCK_DB_SECRET),
                "SecretId": SecretId,
                "VersionId": "test-version-1",
            }
            logger.info(f"Mock: Returning database secret: {MOCK_DB_SECRET}")
            return response
        else:
            logger.warning(f"Mock: Unknown secret ID: {SecretId}")
            raise Exception(
                f"Secrets Manager can't find the specified secret: {SecretId}"
            )


class MockS3Client:
    """Mock AWS S3 client"""

    def __init__(self, **kwargs):
        logger.info("Created mock S3 client")

    def get_object(self, Bucket, Key):
        """Mock get_object method"""
        logger.info(f"Mock: Getting S3 object from bucket '{Bucket}', key '{Key}'")
        # Return empty mock response
        return {"Body": MagicMock(), "ContentLength": 0}

    def put_object(self, Bucket, Key, Body):
        """Mock put_object method"""
        logger.info(f"Mock: Putting S3 object to bucket '{Bucket}', key '{Key}'")
        return {"ETag": "mock-etag", "VersionId": "mock-version"}


class MockSNSClient:
    """Mock AWS SNS client"""

    def __init__(self, **kwargs):
        logger.info("Created mock SNS client")

    def publish(self, TopicArn, Message, Subject=None):
        """Mock publish method"""
        logger.info(f"Mock: Publishing SNS message to topic '{TopicArn}'")
        logger.info(
            f"Mock: Message: {Message[:100]}..."
            if len(Message) > 100
            else f"Mock: Message: {Message}"
        )
        return {"MessageId": "mock-message-id"}


class MockSQSClient:
    """Mock AWS SQS client"""

    def __init__(self, **kwargs):
        logger.info("Created mock SQS client")

    def send_message(self, QueueUrl, MessageBody):
        """Mock send_message method"""
        logger.info(f"Mock: Sending SQS message to queue '{QueueUrl}'")
        return {"MessageId": "mock-message-id"}


# Mock client factory
def mock_client(service_name, **kwargs):
    """Mock boto3.client function"""
    logger.info(f"Mock: Creating {service_name} client with args: {kwargs}")

    if service_name == "secretsmanager":
        return MockSecretsManagerClient(**kwargs)
    elif service_name == "s3":
        return MockS3Client(**kwargs)
    elif service_name == "sns":
        return MockSNSClient(**kwargs)
    elif service_name == "sqs":
        return MockSQSClient(**kwargs)
    else:
        logger.warning(f"Mock: Unknown service: {service_name}")
        return MagicMock()


# Mock resource factory
def mock_resource(service_name, **kwargs):
    """Mock boto3.resource function"""
    logger.info(f"Mock: Creating {service_name} resource with args: {kwargs}")
    return MagicMock()


# Mock session
class MockSession:
    """Mock boto3 Session"""

    def __init__(self, **kwargs):
        logger.info("Created mock boto3 Session")

    def client(self, service_name, **kwargs):
        return mock_client(service_name, **kwargs)

    def resource(self, service_name, **kwargs):
        return mock_resource(service_name, **kwargs)


# Export the mock functions
client = mock_client
resource = mock_resource
Session = MockSession
