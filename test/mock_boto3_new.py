"""
Mock boto3 module that intercepts AWS Secrets Manager calls
and returns local database credentials instead.
This allows existing scripts to run without modification.
"""
import json
import os

# Store original boto3 for fallback if needed
try:
    import boto3 as _original_boto3
    import botocore as _original_botocore
except ImportError:
    _original_boto3 = None
    _original_botocore = None

class MockSecretsManagerClient:
    """Mock AWS Secrets Manager client that returns local DB credentials"""
    
    def get_secret_value(self, SecretId=None, **kwargs):
        """Return local database credentials in the expected format"""
        if SecretId == "local-test-secret" or SecretId == os.environ.get("DB_SECRET_ARN"):
            secret_data = {
                "host": "localhost",  # Use localhost to connect to host port
                "port": "15432",      # Use the host port binding we set in docker-compose
                "username": "stocksuser",
                "password": "stockspass",
                "dbname": "stocksdb"
            }
            return {
                "SecretString": json.dumps(secret_data)
            }
        else:
            raise Exception(f"Secret {SecretId} not found in mock environment")

class MockBoto3:
    """Mock boto3 module that provides our mock clients"""
    
    @staticmethod
    def client(service_name, **kwargs):
        """Return mock clients for AWS services"""
        if service_name == "secretsmanager":
            return MockSecretsManagerClient()
        else:
            # For other services, try to use real boto3 if available
            if _original_boto3:
                return _original_boto3.client(service_name, **kwargs)
            else:
                raise Exception(f"Mock not implemented for service: {service_name}")

# Replace the boto3 module in sys.modules
import sys
sys.modules['boto3'] = MockBoto3()

# Also provide the mock classes for direct import
client = MockBoto3.client
