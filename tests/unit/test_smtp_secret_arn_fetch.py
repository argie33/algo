"""Regression: get_smtp_credentials() had no code path that ever consumed
ALERT_SMTP_SECRET_ARN. terraform/modules/services/main.tf stores SMTP credentials in AWS
Secrets Manager (JSON blob: {password, username, host, port}) specifically so the
password isn't visible via lambda:GetFunction, and sets ALERT_SMTP_SECRET_ARN on the
orchestrator Lambda's env - deliberately NOT ALERT_SMTP_PASSWORD. Without this fetch,
AlertManager's self.smtp_password was always empty in the real deployed Lambda even with
everything correctly configured in terraform/IAM, silently disabling email alerts.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from algo.config.credential_manager import CredentialManager


def test_smtp_credentials_fetched_from_secrets_manager_when_arn_set():
    mgr = CredentialManager()
    mgr._is_aws = True

    mock_response = {
        "SecretString": json.dumps(
            {"host": "smtp.example.com", "port": "587", "username": "alerts@example.com", "password": "s3cr3t"}
        )
    }

    with patch.dict(
        os.environ,
        {"ALERT_SMTP_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:algo-smtp"},
        clear=True,
    ):
        with patch.object(mgr, "_get_secrets_client") as mock_get_client:
            mock_sm = MagicMock()
            mock_get_client.return_value = mock_sm
            mock_sm.get_secret_value.return_value = mock_response

            creds = mgr.get_smtp_credentials()

    assert creds == {
        "username": "alerts@example.com",
        "password": "s3cr3t",
        "host": "smtp.example.com",
        "port": 587,
    }


def test_smtp_secret_missing_field_raises():
    mgr = CredentialManager()
    mgr._is_aws = True

    mock_response = {"SecretString": json.dumps({"host": "smtp.example.com", "port": "587"})}  # missing username/password

    with patch.dict(
        os.environ,
        {"ALERT_SMTP_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:algo-smtp"},
        clear=True,
    ):
        with patch.object(mgr, "_get_secrets_client") as mock_get_client:
            mock_sm = MagicMock()
            mock_get_client.return_value = mock_sm
            mock_sm.get_secret_value.return_value = mock_response

            with pytest.raises(ValueError, match="missing required field"):
                mgr.get_smtp_credentials()


def test_smtp_falls_back_to_env_vars_when_not_in_aws():
    """Local dev / test: ALERT_SMTP_SECRET_ARN may be set but _is_aws=False, or unset -
    either way, individual env vars must still work (existing behavior preserved)."""
    mgr = CredentialManager()
    mgr._is_aws = False

    with patch.dict(
        os.environ,
        {
            "ALERT_SMTP_HOST": "mail.local",
            "ALERT_SMTP_USER": "user",
            "ALERT_SMTP_PASSWORD": "pass",
            "ALERT_SMTP_PORT": "25",
        },
        clear=True,
    ):
        creds = mgr.get_smtp_credentials()

    assert creds == {"username": "user", "password": "pass", "host": "mail.local", "port": 25}
