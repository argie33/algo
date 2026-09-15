"""XBRL US client: credential validation and access-token lifecycle (cache hit/expiry/refresh).

Added 2026-09-15 (/goal "get our XBRL data handling all right" session) alongside
utils/external/xbrl_us_client.py itself - the OAuth2 token-caching logic is the one piece of
that module worth unit-testing in isolation (the actual HTTP calls to api.xbrl.us are covered
by live manual verification against a real account, documented in that module's own docstring,
not repeated here as a mock-only test that would just assert our own mock's behavior).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from utils.external import xbrl_us_client


class TestCredentialValidation:
    def test_missing_all_credentials_raises_with_field_names(self, monkeypatch):
        for var in ("XBRL_US_CLIENT_ID", "XBRL_US_CLIENT_SECRET", "XBRL_US_USERNAME", "XBRL_US_PASSWORD"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(RuntimeError) as exc_info:
            xbrl_us_client._load_credentials()
        for field in ("client_id", "client_secret", "username", "password"):
            assert field in str(exc_info.value)

    def test_partial_credentials_names_only_the_missing_ones(self, monkeypatch):
        monkeypatch.setenv("XBRL_US_CLIENT_ID", "id")
        monkeypatch.setenv("XBRL_US_CLIENT_SECRET", "secret")
        monkeypatch.delenv("XBRL_US_USERNAME", raising=False)
        monkeypatch.delenv("XBRL_US_PASSWORD", raising=False)
        with pytest.raises(RuntimeError) as exc_info:
            xbrl_us_client._load_credentials()
        assert "username" in str(exc_info.value)
        assert "password" in str(exc_info.value)
        assert "client_id" not in str(exc_info.value)

    def test_all_credentials_present_returns_them(self, monkeypatch):
        monkeypatch.setenv("XBRL_US_CLIENT_ID", "id")
        monkeypatch.setenv("XBRL_US_CLIENT_SECRET", "secret")
        monkeypatch.setenv("XBRL_US_USERNAME", "user")
        monkeypatch.setenv("XBRL_US_PASSWORD", "pass")
        creds = xbrl_us_client._load_credentials()
        assert creds == {"client_id": "id", "client_secret": "secret", "username": "user", "password": "pass"}


class TestAccessTokenLifecycle:
    def test_fresh_cached_token_is_reused_without_a_network_call(self, monkeypatch, tmp_path):
        cache_file = tmp_path / "token.json"
        monkeypatch.setattr(xbrl_us_client, "_TOKEN_CACHE_PATH", cache_file)
        xbrl_us_client._write_token_cache(
            {
                "access_token": "cached-token",
                "refresh_token": "cached-refresh",
                "expires_in": 3600,
                "refresh_token_expires_in": 1209600,
                "_obtained_at": time.time(),
            }
        )
        with patch("utils.external.xbrl_us_client.requests.post") as mock_post:
            token = xbrl_us_client._get_access_token()
        assert token == "cached-token"
        mock_post.assert_not_called()

    def test_expired_access_token_triggers_refresh_grant(self, monkeypatch, tmp_path):
        cache_file = tmp_path / "token.json"
        monkeypatch.setattr(xbrl_us_client, "_TOKEN_CACHE_PATH", cache_file)
        xbrl_us_client._write_token_cache(
            {
                "access_token": "old-token",
                "refresh_token": "still-valid-refresh",
                "expires_in": 3600,
                "refresh_token_expires_in": 1209600,
                "_obtained_at": time.time() - 4000,  # access token expired, refresh still valid
            }
        )
        monkeypatch.setenv("XBRL_US_CLIENT_ID", "id")
        monkeypatch.setenv("XBRL_US_CLIENT_SECRET", "secret")
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {
            "access_token": "refreshed-token",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
            "refresh_token_expires_in": 1209600,
        }
        with patch("utils.external.xbrl_us_client.requests.post", return_value=mock_response) as mock_post:
            token = xbrl_us_client._get_access_token()
        assert token == "refreshed-token"
        assert mock_post.call_args.kwargs["data"]["grant_type"] == "refresh_token"
        assert mock_post.call_args.kwargs["data"]["refresh_token"] == "still-valid-refresh"

    def test_expired_refresh_token_falls_back_to_password_grant(self, monkeypatch, tmp_path):
        cache_file = tmp_path / "token.json"
        monkeypatch.setattr(xbrl_us_client, "_TOKEN_CACHE_PATH", cache_file)
        xbrl_us_client._write_token_cache(
            {
                "access_token": "old-token",
                "refresh_token": "expired-refresh",
                "expires_in": 3600,
                "refresh_token_expires_in": 1209600,
                "_obtained_at": time.time() - 2_000_000,  # both access and refresh expired
            }
        )
        monkeypatch.setenv("XBRL_US_CLIENT_ID", "id")
        monkeypatch.setenv("XBRL_US_CLIENT_SECRET", "secret")
        monkeypatch.setenv("XBRL_US_USERNAME", "user")
        monkeypatch.setenv("XBRL_US_PASSWORD", "pass")
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {
            "access_token": "brand-new-token",
            "refresh_token": "brand-new-refresh",
            "expires_in": 3600,
            "refresh_token_expires_in": 1209600,
        }
        with patch("utils.external.xbrl_us_client.requests.post", return_value=mock_response) as mock_post:
            token = xbrl_us_client._get_access_token()
        assert token == "brand-new-token"
        assert mock_post.call_args.kwargs["data"]["grant_type"] == "password"

    def test_no_cache_file_goes_straight_to_password_grant(self, monkeypatch, tmp_path):
        cache_file = tmp_path / "nonexistent" / "token.json"
        monkeypatch.setattr(xbrl_us_client, "_TOKEN_CACHE_PATH", cache_file)
        monkeypatch.setenv("XBRL_US_CLIENT_ID", "id")
        monkeypatch.setenv("XBRL_US_CLIENT_SECRET", "secret")
        monkeypatch.setenv("XBRL_US_USERNAME", "user")
        monkeypatch.setenv("XBRL_US_PASSWORD", "pass")
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {
            "access_token": "first-token",
            "refresh_token": "first-refresh",
            "expires_in": 3600,
            "refresh_token_expires_in": 1209600,
        }
        with patch("utils.external.xbrl_us_client.requests.post", return_value=mock_response):
            token = xbrl_us_client._get_access_token()
        assert token == "first-token"
        assert cache_file.exists()

    def test_auth_failure_raises_xbrl_us_auth_error(self, monkeypatch):
        monkeypatch.setenv("XBRL_US_CLIENT_ID", "id")
        monkeypatch.setenv("XBRL_US_CLIENT_SECRET", "bad-secret")
        mock_response = MagicMock(status_code=401, text="invalid_client")
        with patch("utils.external.xbrl_us_client.requests.post", return_value=mock_response):
            with pytest.raises(xbrl_us_client.XbrlUsAuthError, match="401"):
                xbrl_us_client._request_token("refresh_token", refresh_token="whatever")
