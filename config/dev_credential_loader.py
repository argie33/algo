#!/usr/bin/env python3
"""
Dev bypass mode credential loader.

Extends credential_manager with local caching and fallback for development.
When DEV_BYPASS_MODE is enabled, credentials are cached locally with TTL,
reducing AWS API calls and enabling offline development.

Features:
- Local file-based cache with TTL (default 24h)
- Automatic fallback to test credentials (DEV_TEST_CREDENTIALS env var)
- Graceful degradation if AWS unreachable
- Non-breaking integration with existing credential_manager

Environment variables:
- DEV_BYPASS_MODE: Enable dev cache (true/false)
- DEV_CACHE_DIR: Override cache location (default ~/.aws-dev)
- DEV_CACHE_TTL_HOURS: Override cache TTL (default 24)
- DEV_TEST_CREDENTIALS: JSON-encoded test credentials for fallback
- DEV_CACHE_DEBUG: Enable verbose logging (true/false)
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# Parse environment
DEV_BYPASS_MODE = os.getenv("DEV_BYPASS_MODE", "").lower() in ("true", "1", "yes")
DEV_CACHE_DIR = Path(os.getenv("DEV_CACHE_DIR", "~/.aws-dev")).expanduser()
DEV_CACHE_TTL_HOURS = int(os.getenv("DEV_CACHE_TTL_HOURS", "24"))
DEV_CACHE_DEBUG = os.getenv("DEV_CACHE_DEBUG", "").lower() in ("true", "1", "yes")


class DevCredentialLoader:
    """Local credential caching for development."""

    def __init__(
        self, cache_dir: Path = DEV_CACHE_DIR, ttl_hours: int = DEV_CACHE_TTL_HOURS
    ):
        self.cache_dir = Path(cache_dir).expanduser()
        self.ttl_hours = ttl_hours
        self.cache_file = self.cache_dir / "secrets-cache.json"
        self.debug = DEV_CACHE_DEBUG

    def _log(self, msg: str, level: str = "debug"):
        """Log with [DEV_CACHE] prefix."""
        if level == "debug" and not self.debug:
            return
        prefix = "[DEV_CACHE]"
        getattr(logger, level)(f"{prefix} {msg}")

    def _ensure_cache_dir(self):
        """Create cache directory if missing."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cached_secret(self, secret_name: str) -> Optional[Dict[str, str]]:
        """
        Load secret from cache if fresh.

        Args:
            secret_name: e.g., 'algo/database', 'algo/alpaca'

        Returns:
            Secret dict if cached and fresh, None otherwise
        """
        if not DEV_BYPASS_MODE:
            self._log("Dev bypass disabled; skipping cache", level="debug")
            return None

        try:
            if not self.cache_file.exists():
                self._log(f"Cache file not found: {self.cache_file}", level="debug")
                return None

            with open(self.cache_file) as f:
                cache = json.load(f)

            if secret_name not in cache:
                self._log(f"Secret not in cache: {secret_name}", level="debug")
                return None

            entry = cache[secret_name]
            expires_at = float(entry.get("expires_at", 0))
            now = time.time()

            if now >= expires_at:
                self._log(f"Cache expired for {secret_name}", level="debug")
                return None

            hours_until_expiry = (expires_at - now) / 3600
            self._log(
                f"Cache hit for {secret_name} (expires in {hours_until_expiry:.1f}h)",
                level="debug",
            )
            return entry.get("value", {})

        except Exception as e:
            self._log(f"Failed to load cache: {e}", level="warning")
            return None

    def set_cached_secret(self, secret_name: str, value: Dict[str, str]):
        """
        Store secret in cache.

        Args:
            secret_name: e.g., 'algo/database', 'algo/alpaca'
            value: Secret value (dict or string)
        """
        if not DEV_BYPASS_MODE:
            return

        try:
            self._ensure_cache_dir()

            # Load existing cache or create new
            cache = {}
            if self.cache_file.exists():
                with open(self.cache_file) as f:
                    cache = json.load(f)

            # Add/update entry with TTL
            now = time.time()
            expires_at = now + (self.ttl_hours * 3600)

            cache[secret_name] = {
                "value": value if isinstance(value, dict) else {"result": str(value)},
                "cached_at": now,
                "expires_at": expires_at,
                "ttl_hours": self.ttl_hours,
            }

            # Write cache atomically
            with open(self.cache_file, "w") as f:
                json.dump(cache, f, indent=2)

            self._log(f"Cached {secret_name} (TTL: {self.ttl_hours}h)", level="debug")

        except Exception as e:
            self._log(f"Failed to cache secret: {e}", level="warning")

    def get_test_credentials(self) -> Optional[Dict[str, str]]:
        """
        Load test/fallback credentials from DEV_TEST_CREDENTIALS env var.

        Format: JSON-encoded dict with AWS keys (non-functional for real AWS, for dev only)
        """
        test_creds_json = os.getenv("DEV_TEST_CREDENTIALS", "")
        if not test_creds_json:
            return None

        try:
            creds = json.loads(test_creds_json)
            self._log("Using test fallback credentials (non-functional)", level="debug")
            return creds
        except json.JSONDecodeError as e:
            self._log(f"Failed to parse DEV_TEST_CREDENTIALS: {e}", level="warning")
            return None

    def get_secret_with_fallback(
        self, secret_name: str, fetch_from_aws_fn, default: Optional[str] = None
    ) -> Optional[Any]:
        """
        Fetch secret with fallback chain:
        1. Local cache (if fresh)
        2. AWS Secrets Manager (via provided function)
        3. Test credentials (if DEV_BYPASS_MODE)
        4. Default value
        5. Error

        Args:
            secret_name: Name of secret
            fetch_from_aws_fn: Callable that fetches from AWS (signature: (secret_name) -> Optional[str])
            default: Default value if all else fails

        Returns:
            Secret value or default
        """
        if not DEV_BYPASS_MODE:
            # Normal flow: skip cache, go straight to AWS
            return fetch_from_aws_fn(secret_name)

        # Try cache first
        cached = self.get_cached_secret(secret_name)
        if cached:
            # Cache stores secrets as dicts, return as-is for structured secrets
            return cached if isinstance(cached, dict) else cached.get("result")

        # Try AWS
        try:
            self._log(f"Fetching fresh: {secret_name}", level="debug")
            secret = fetch_from_aws_fn(secret_name)
            if secret:
                self.set_cached_secret(secret_name, secret)
                return secret
        except Exception as e:
            self._log(f"Failed to fetch from AWS: {e}", level="warning")

        # Try test credentials
        test_creds = self.get_test_credentials()
        if test_creds:
            self._log(f"Using test credentials for {secret_name}", level="info")
            return test_creds

        # Return default
        return default

    def clear_cache(self):
        """Clear all cached secrets."""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
                self._log("Cleared all cached secrets", level="info")
        except Exception as e:
            self._log(f"Failed to clear cache: {e}", level="warning")

    def get_cache_status(self) -> Dict[str, Any]:
        """Get cache status (age, TTL, entries)."""
        if not self.cache_file.exists():
            return {"cache_exists": False, "entries": 0}

        try:
            with open(self.cache_file) as f:
                cache = json.load(f)

            now = time.time()
            fresh_entries = 0
            stale_entries = 0

            for name, entry in cache.items():
                if now < float(entry.get("expires_at", 0)):
                    fresh_entries += 1
                else:
                    stale_entries += 1

            return {
                "cache_exists": True,
                "entries": len(cache),
                "fresh_entries": fresh_entries,
                "stale_entries": stale_entries,
            }
        except Exception as e:
            logger.warning(f"Failed to read cache status: {e}")
            return {"cache_exists": False, "error": str(e)}


# Singleton instance
_dev_loader = None


def get_dev_loader() -> DevCredentialLoader:
    """Get or create dev credential loader singleton."""
    global _dev_loader
    if _dev_loader is None:
        _dev_loader = DevCredentialLoader()
    return _dev_loader
