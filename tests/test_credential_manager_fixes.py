#!/usr/bin/env python3
"""Test credential manager fixes for explicit validation without fallback chains."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from config.credential_manager import CredentialManager


def test_db_credentials_requires_all_fields_in_aws_secret():
    """Verify that missing fields in AWS secret raise errors, not silently default."""
    mgr = CredentialManager()
    mgr._is_aws = True

    mock_response_incomplete = {"SecretString": json.dumps({"host": "db.local"})}

    with patch.dict(
        os.environ,
        {"DB_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:db-creds"},
        clear=False,
    ):
        with patch.object(mgr, "_get_secrets_client") as mock_client:
            mock_sm = MagicMock()
            mock_client.return_value = mock_sm
            mock_sm.get_secret_value.return_value = mock_response_incomplete

            with pytest.raises(RuntimeError, match="Failed to load database credentials"):
                mgr.get_db_credentials()


def test_db_credentials_requires_port_is_valid_integer():
    """Verify that invalid port values raise errors."""
    mgr = CredentialManager()
    mgr._is_aws = True

    mock_response = {
        "SecretString": json.dumps(
            {
                "host": "db.local",
                "port": "not-a-number",
                "username": "user",
                "password": "pass",
                "dbname": "stocks",
            }
        )
    }

    with patch.dict(
        os.environ,
        {"DB_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:db-creds"},
        clear=False,
    ):
        with patch.object(mgr, "_get_secrets_client") as mock_client:
            mock_sm = MagicMock()
            mock_client.return_value = mock_sm
            mock_sm.get_secret_value.return_value = mock_response

            with pytest.raises(RuntimeError, match="Failed to load database credentials"):
                mgr.get_db_credentials()


def test_db_credentials_local_requires_all_env_vars():
    """Verify that local dev mode requires ALL env vars, no defaults."""
    mgr = CredentialManager()
    mgr._is_aws = False

    # Set up minimal env vars, missing DB_NAME
    with patch.dict(
        os.environ,
        {
            "DB_HOST": "localhost",
            "DB_PORT": "5432",
            "DB_USER": "testuser",
            "DB_PASSWORD": "testpass",
        },
        clear=True,
    ):
        # Mock the get_password call to return the password
        with patch.object(mgr, "get_password", return_value="testpass"):
            with pytest.raises(ValueError, match="DB_NAME not set"):
                mgr.get_db_credentials()


def test_fetch_secrets_manager_requires_secret_string_or_binary():
    """Verify that empty secrets (no SecretString/Binary) fail explicitly."""
    mgr = CredentialManager()

    mock_response = {}  # No SecretString or SecretBinary

    with patch.object(mgr, "_get_secrets_client") as mock_client:
        mock_sm = MagicMock()
        mock_client.return_value = mock_sm
        mock_sm.get_secret_value.return_value = mock_response

        with pytest.raises(RuntimeError, match="Credential retrieval failed"):
            mgr._fetch_from_secrets_manager("test/secret")


def test_alpaca_secrets_validate_all_required_fields():
    """Verify that Alpaca secrets with incomplete data raise validation errors."""
    mgr = CredentialManager()
    mgr._is_aws = True

    # Secret with only api_key, missing api_secret - should fail validation
    incomplete_response = {"SecretString": json.dumps({"api_key": "test-key"})}

    with patch.object(mgr, "_get_secrets_client") as mock_client:
        mock_sm = MagicMock()
        mock_client.return_value = mock_sm

        # Create a custom ResourceNotFoundError class
        class ResourceNotFoundError(Exception):
            pass

        mock_sm.exceptions.ResourceNotFoundException = ResourceNotFoundError

        call_count = 0
        def mock_get_secret_value(secret_id):
            nonlocal call_count
            call_count += 1
            # First call (user-specific) returns incomplete data
            if call_count == 1:
                return incomplete_response
            # All other calls raise ResourceNotFound
            raise ResourceNotFoundError("Secret not found")

        mock_sm.get_secret_value.side_effect = mock_get_secret_value

        # With all sources failing, should get final error about no credentials
        with pytest.raises(ValueError):
            mgr.get_alpaca_credentials(user_id="test-user")


def test_smtp_credentials_requires_all_fields_if_any_set():
    """Verify that partial SMTP config raises error, not partial dict."""
    mgr = CredentialManager()

    # Set only host, missing user/password/port
    with patch.dict(
        os.environ,
        {"ALERT_SMTP_HOST": "mail.local"},
        clear=True,
    ):
        with pytest.raises(ValueError, match="ALERT_SMTP_USER is not set"):
            mgr.get_smtp_credentials()


def test_smtp_credentials_port_must_be_valid_integer():
    """Verify SMTP port validation."""
    mgr = CredentialManager()

    with patch.dict(
        os.environ,
        {
            "ALERT_SMTP_HOST": "mail.local",
            "ALERT_SMTP_USER": "user",
            "ALERT_SMTP_PASSWORD": "pass",
            "ALERT_SMTP_PORT": "not-a-port",
        },
        clear=True,
    ):
        with pytest.raises(ValueError, match="must be a valid integer"):
            mgr.get_smtp_credentials()


def test_db_credentials_aws_requires_secret_string():
    """Verify that AWS secrets without SecretString raise error."""
    mgr = CredentialManager()
    mgr._is_aws = True

    mock_response = {"SecretBinary": b"data"}  # Only binary, no string

    with patch.dict(
        os.environ,
        {"DB_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:db-creds"},
        clear=False,
    ):
        with patch.object(mgr, "_get_secrets_client") as mock_client:
            mock_sm = MagicMock()
            mock_client.return_value = mock_sm
            mock_sm.get_secret_value.return_value = mock_response

            with pytest.raises(RuntimeError, match="Failed to load database credentials"):
                mgr.get_db_credentials()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
