#!/usr/bin/env python3
"""Pytest configuration with AWS mocking for all tests."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

# Set environment FIRST
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5432"
os.environ["DB_NAME"] = "algo_trading"
os.environ["DB_USER"] = "postgres"
os.environ["DB_PASSWORD"] = "test_password"
os.environ["ALPACA_API_KEY"] = "PK_TEST"
os.environ["ALPACA_SECRET_KEY"] = "sk_test"
os.environ["AWS_REGION"] = "us-east-1"

# Pytest hook: set up mocks BEFORE any test collection
def pytest_configure(config):
    """Configure mocks at pytest startup, before any module imports."""
    from unittest.mock import MagicMock

    # Mock boto3 globally
    import boto3
    original_client = boto3.client

    def mock_client(service_name, **kwargs):
        if service_name == "secretsmanager":
            mock = MagicMock()
            mock.get_secret_value.return_value = {
                "SecretString": '{"host":"localhost","port":5432,"user":"postgres","password":"test_password"}'
            }
            return mock
        return original_client(service_name, **kwargs)

    boto3.client = mock_client

    # Mock psycopg2
    import psycopg2
    original_connect = psycopg2.connect

    def mock_connect(*args, **kwargs):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn

    psycopg2.connect = mock_connect

# Patch boto3 BEFORE any imports that use it
import boto3
_original_boto3_client = boto3.client

def mock_boto3_client(service_name, **kwargs):
    if service_name == "secretsmanager":
        mock_sm = MagicMock()
        def mock_get_secret(SecretId, **kw):
            secrets = {
                "algo/db-credentials-prod": {
                    "SecretString": '{"host":"localhost","port":5432,"user":"postgres","password":"test_password","database":"algo_trading"}'
                },
                "algo/alpaca-credentials": {
                    "SecretString": '{"api_key":"PK_TESTMODE","secret_key":"sk_test"}'
                },
            }
            if SecretId in secrets:
                return secrets[SecretId]
            raise Exception(f"Secret {SecretId} not found")
        mock_sm.get_secret_value = mock_get_secret
        return mock_sm
    return _original_boto3_client(service_name, **kwargs)

boto3.client = mock_boto3_client

# Also mock psycopg2 connections
import psycopg2
_original_psycopg2_connect = psycopg2.connect

def mock_psycopg2_connect(*args, **kwargs):
    """Return a mock connection for all database calls."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    mock_cursor.description = None
    mock_cursor.rowcount = 0
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.commit.return_value = None
    mock_conn.close.return_value = None
    return mock_conn

psycopg2.connect = mock_psycopg2_connect
sys.modules["psycopg2"].connect = mock_psycopg2_connect


@pytest.fixture
def mock_db():
    """Mock database context."""
    from unittest import mock

    with mock.patch("utils.db.DatabaseContext") as m:
        yield m
