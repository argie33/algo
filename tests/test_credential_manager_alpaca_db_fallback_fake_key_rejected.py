#!/usr/bin/env python3
"""Regression test for the 2026-08-21 fix (goal session - "digging into the logs" audit):
get_alpaca_credentials()'s database-fallback tier (Step 4, reading algo_config) silently
accepted the exact placeholder is_obviously_fake_alpaca_key() was built to catch
("PK0123456789ABCDEF" / "test_..." secrets) - that detector only ever guarded
orchestrator.py's separate, stricter execution_mode="auto" startup gate, never this tier.

Live-confirmed: this exact fake key sat in algo_config.alpaca_api_key (seeded 2026-07-11)
and was silently returned as if valid whenever the earlier credential tiers failed (e.g.
.env.local not yet loaded into the process environment) - causing real HTTP 401s from
Alpaca on every price_daily request all day, with the loader falling back to yfinance
alone and missing ~325 symbols (6.4%) it otherwise would have gotten from Alpaca.

Fix: get_alpaca_credentials() now rejects an is_obviously_fake_alpaca_key() match (or a
secret starting with "test_") from the database fallback tier instead of returning it.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from algo.config.credential_manager import CredentialManager


def _mgr_with_no_aws_no_env() -> CredentialManager:
    mgr = CredentialManager()
    mgr._is_aws = False
    return mgr


def _patch_psycopg2_rows(key_value, secret_value):
    """Build a psycopg2.connect mock whose cursor returns the given key/secret rows in
    sequence, matching get_alpaca_credentials()'s two SELECT ... WHERE key = %s calls."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [
        (key_value,) if key_value is not None else None,
        (secret_value,) if secret_value is not None else None,
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return patch("psycopg2.connect", return_value=mock_conn)


class TestAlpacaDatabaseFallbackFakeKeyRejected:
    def test_sequential_placeholder_key_rejected_from_db_fallback(self):
        """The exact live-confirmed placeholder - must not be returned as valid."""
        mgr = _mgr_with_no_aws_no_env()
        with patch.dict(os.environ, {}, clear=True):
            with _patch_psycopg2_rows("PK0123456789ABCDEF", "some_secret_value_here_1234"):
                with pytest.raises(ValueError):
                    mgr.get_alpaca_credentials()

    def test_test_prefixed_secret_rejected_from_db_fallback(self):
        """A real-looking key paired with an obviously-fake 'test_' secret must also be
        rejected - the placeholder signal isn't only in the key."""
        mgr = _mgr_with_no_aws_no_env()
        with patch.dict(os.environ, {}, clear=True):
            with _patch_psycopg2_rows("PKX7QM2NF9WZLR4KDT8B", "test_secret_placeholder_value"):
                with pytest.raises(ValueError):
                    mgr.get_alpaca_credentials()

    def test_realistic_credentials_still_accepted_from_db_fallback(self):
        """Regression guard: a real, randomly-generated key/secret pair must still work
        via this fallback tier - the new check must not over-reject legitimate credentials."""
        mgr = _mgr_with_no_aws_no_env()
        with patch.dict(os.environ, {}, clear=True):
            with _patch_psycopg2_rows("PKX7QM2NF9WZLR4KDT8B", "realSecretValueNotAPlaceholder123"):
                creds = mgr.get_alpaca_credentials()
        assert creds == {"key": "PKX7QM2NF9WZLR4KDT8B", "secret": "realSecretValueNotAPlaceholder123"}
