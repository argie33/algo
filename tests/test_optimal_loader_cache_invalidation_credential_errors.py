#!/usr/bin/env python3
"""Regression test: OptimalLoader._invalidate_cache() must treat AWS credential-invalidity
errors (UnrecognizedClientException, InvalidClientTokenId, ExpiredTokenException,
InvalidSignatureException - the family thrown when no real AWS account is configured,
e.g. local dev) the same as AccessDenied: log one WARNING and return, not fall through
to two ERROR-level "cache poisoning failed" log lines on every single loader run.

Before this fix, only AccessDenied/AccessDeniedException were recognized as "no DynamoDB
access, degrade gracefully" - every local-dev run without real AWS credentials hit
UnrecognizedClientException instead, which fell through both branches to
logger.error(...) twice per loader (confirmed live in today's orchestrator dry-run logs).
"""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from utils.optimal_loader import OptimalLoader


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "simulated"}}, "DeleteItem")


class _TestLoader(OptimalLoader):
    table_name = "stock_scores"  # any real SAFE_TABLES entry - required for __init__ validation


class TestCacheInvalidationCredentialErrors:
    @pytest.mark.parametrize(
        "error_code",
        [
            "AccessDenied",
            "AccessDeniedException",
            "UnrecognizedClientException",
            "InvalidClientTokenId",
            "ExpiredTokenException",
            "InvalidSignatureException",
        ],
    )
    def test_no_access_error_codes_degrade_with_single_warning_no_error_log(self, error_code):
        loader = _TestLoader()

        mock_table = MagicMock()
        mock_table.delete_item.side_effect = _client_error(error_code)

        with patch("boto3.resource") as mock_resource, patch("utils.optimal_loader.logger") as mock_logger:
            mock_resource.return_value.Table.return_value = mock_table

            loader._invalidate_cache()

            mock_logger.warning.assert_called_once()
            mock_logger.error.assert_not_called()
            # update_item (the "cache poisoning" fallback) must never be attempted for
            # a recognized no-access error - the WARNING branch returns immediately.
            mock_table.update_item.assert_not_called()

    def test_unrecognized_error_code_still_falls_through_to_poisoning_attempt(self):
        """An error code outside the known no-access set is a real, unexpected failure -
        it should still attempt the cache-poisoning fallback and log at ERROR."""
        loader = _TestLoader()

        mock_table = MagicMock()
        mock_table.delete_item.side_effect = _client_error("ThrottlingException")
        mock_table.update_item.side_effect = _client_error("ThrottlingException")

        with patch("boto3.resource") as mock_resource, patch("utils.optimal_loader.logger") as mock_logger:
            mock_resource.return_value.Table.return_value = mock_table

            loader._invalidate_cache()

            mock_table.update_item.assert_called_once()
            assert mock_logger.error.call_count >= 1
