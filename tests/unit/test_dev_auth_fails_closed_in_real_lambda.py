"""Regression test: dev-mode auth bypass (auto-assigned "dev-admin" claims when no
Authorization header is present, lambda/api/lambda_function.py:1421-1429) must never
activate inside a real deployed AWS Lambda, even if Cognito is misconfigured/missing.

lambda/api/dev_auth.py's is_local_dev_mode() is the single gate all of get_dev_claims()/
validate_dev_token() depend on. Its own docstring claims "In production Lambda, Cognito
MUST be configured (this code is unreachable if properly configured)" - but that safety
property rests entirely on the AWS_LAMBDA_FUNCTION_NAME check forcing is_dev=False
whenever running as a real Lambda, independent of whether COGNITO_USER_POOL_ID happens to
be set. This was previously untested (no unit coverage existed for dev_auth.py at all -
only integration tests for the admin-vs-trader role gating downstream of a caller already
holding valid claims, not this earlier fail-closed gate).

'lambda' is a Python keyword, so the module under test is loaded via importlib.
"""

import importlib
import os
from unittest.mock import patch

dev_auth = importlib.import_module("lambda.api.dev_auth")


class TestIsLocalDevMode:
    def test_real_lambda_with_cognito_configured_is_not_dev_mode(self):
        with patch.dict(
            os.environ,
            {"AWS_LAMBDA_FUNCTION_NAME": "algo-api", "COGNITO_USER_POOL_ID": "us-east-1_real"},
            clear=True,
        ):
            assert dev_auth.is_local_dev_mode() is False

    def test_real_lambda_with_cognito_misconfigured_still_fails_closed(self):
        """CRITICAL: this is the scenario that matters most - a deployment mistake
        (COGNITO_USER_POOL_ID unset/empty) must NOT silently open an admin-access
        bypass in a live Lambda. AWS always sets AWS_LAMBDA_FUNCTION_NAME itself
        (not attacker-controllable), so this must stay the deciding factor."""
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "algo-api"}, clear=True):
            assert dev_auth.is_local_dev_mode() is False

    def test_non_lambda_without_cognito_is_dev_mode(self):
        with patch.dict(os.environ, {}, clear=True):
            assert dev_auth.is_local_dev_mode() is True

    def test_explicit_environment_development_is_dev_mode_even_in_lambda(self):
        """Documented escape hatch - must require an explicit, deliberate env var,
        not just an absent one."""
        with patch.dict(
            os.environ,
            {"AWS_LAMBDA_FUNCTION_NAME": "algo-api", "ENVIRONMENT": "development"},
            clear=True,
        ):
            assert dev_auth.is_local_dev_mode() is True


class TestGetDevClaimsFailsClosedInRealLambda:
    def test_dev_admin_token_rejected_in_real_lambda(self):
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "algo-api"}, clear=True):
            assert dev_auth.get_dev_claims("dev-admin") is None

    def test_validate_dev_token_rejected_in_real_lambda(self):
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "algo-api"}, clear=True):
            is_valid, claims, error = dev_auth.validate_dev_token("dev-admin")
            assert is_valid is False
            assert claims is None
            assert error is not None

    def test_dev_admin_token_accepted_outside_lambda_without_cognito(self):
        """Sanity check the positive case still works (local dev_server.py flow)."""
        with patch.dict(os.environ, {}, clear=True):
            claims = dev_auth.get_dev_claims("dev-admin")
            assert claims is not None
            assert claims["sub"] == "dev-admin"
            assert "admin" in claims["cognito:groups"]
