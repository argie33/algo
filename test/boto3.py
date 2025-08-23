# This file ensures that any import of 'boto3' in test scripts uses the mock implementation.

import os
import sys

# Ensure the test directory is in the path so we can import mock_boto3
sys.path.insert(0, os.path.dirname(__file__))

import mock_boto3


# Provide the same interface as real boto3
def client(service_name, *args, **kwargs):
    return mock_boto3.mock_client(service_name, *args, **kwargs)


def resource(service_name, *args, **kwargs):
    return mock_boto3.mock_resource(service_name, *args, **kwargs)


class Session(mock_boto3.MockSession):
    pass
