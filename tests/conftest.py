#!/usr/bin/env python3
"""Pytest configuration with environment setup for credential validation."""

import os
import sys
from pathlib import Path

import pytest

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

# Set valid environment variables BEFORE pytest processes anything
# These bypass credential validation for testing
os.environ["ALPACA_API_KEY"] = "PK_TESTMODEXXXXXXXXXXXXXXXXXX"
os.environ["ALPACA_SECRET_KEY"] = "sk_test_1234567890abcdef1234567890abcdef12345678"
os.environ["DB_HOST"] = "algo-prod.cluster-abc123.us-east-1.rds.amazonaws.com"
os.environ["DB_PORT"] = "5432"
os.environ["DB_NAME"] = "algo_trading"
os.environ["DB_USER"] = "postgres"
os.environ["DB_PASSWORD"] = "Test_Password_1234567890_For_Testing"
os.environ["AWS_ACCESS_KEY_ID"] = "AKIAIOSFODNN7EXAMPLE"
os.environ["AWS_SECRET_ACCESS_KEY"] = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
os.environ["AWS_REGION"] = "us-east-1"


@pytest.fixture
def mock_db():
    """Mock database context."""
    from unittest import mock
    with mock.patch("utils.db.DatabaseContext") as m:
        yield m
