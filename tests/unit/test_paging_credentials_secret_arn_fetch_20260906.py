"""Regression test: get_paging_credentials() must fetch PagerDuty/Twilio credentials from
Secrets Manager when PAGING_SECRET_ARN is set (AWS), and fall back to plain env vars
otherwise (local dev) - mirroring get_smtp_credentials()'s exact pattern
(test_smtp_secret_arn_fetch.py), for the same reason: PAGERDUTY_ROUTING_KEY and
TWILIO_AUTH_TOKEN are secrets that must not be raw Lambda environment variables, which are
visible to anyone with lambda:GetFunction permission.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from algo.config.credential_manager import CredentialManager


def test_paging_credentials_fetched_from_secrets_manager_when_arn_set():
    mgr = CredentialManager()
    mgr._is_aws = True

    mock_response = {
        "SecretString": json.dumps(
            {
                "pagerduty_routing_key": "pd-routing-key",
                "twilio_account_sid": "AC123",
                "twilio_auth_token": "tok123",
                "twilio_from_number": "+15559990000",
                "sms_to": "+15550001111,+15550002222",
            }
        )
    }

    with patch.dict(
        os.environ,
        {"PAGING_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:algo-paging"},
        clear=True,
    ):
        with patch.object(mgr, "_get_secrets_client") as mock_get_client:
            mock_sm = MagicMock()
            mock_get_client.return_value = mock_sm
            mock_sm.get_secret_value.return_value = mock_response

            creds = mgr.get_paging_credentials()

    assert creds == {
        "pagerduty_routing_key": "pd-routing-key",
        "twilio_account_sid": "AC123",
        "twilio_auth_token": "tok123",
        "twilio_from_number": "+15559990000",
        "sms_to": "+15550001111,+15550002222",
    }


def test_paging_credentials_falls_back_to_env_vars_when_not_in_aws():
    mgr = CredentialManager()
    mgr._is_aws = False

    with patch.dict(
        os.environ,
        {
            "PAGERDUTY_ROUTING_KEY": "env-routing-key",
            "TWILIO_ACCOUNT_SID": "",
            "TWILIO_AUTH_TOKEN": "",
            "TWILIO_FROM_NUMBER": "",
            "ALERT_SMS_TO": "",
        },
        clear=True,
    ):
        creds = mgr.get_paging_credentials()

    assert creds is not None
    assert creds["pagerduty_routing_key"] == "env-routing-key"
    assert creds["twilio_account_sid"] == ""


def test_paging_credentials_missing_secret_string_raises():
    mgr = CredentialManager()
    mgr._is_aws = True

    with patch.dict(os.environ, {"PAGING_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123:secret:x"}, clear=True):
        with patch.object(mgr, "_get_secrets_client") as mock_get_client:
            mock_sm = MagicMock()
            mock_get_client.return_value = mock_sm
            mock_sm.get_secret_value.return_value = {}

            with pytest.raises(ValueError, match="no SecretString"):
                mgr.get_paging_credentials()
