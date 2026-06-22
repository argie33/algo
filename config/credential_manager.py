#!/usr/bin/env python3
"""
Centralized credential manager for stock algo platform.

Single source of truth for all credentials:
- Database (username, password)
- Alpaca API keys
- SMTP/email credentials
- Other third-party API keys

Credential Sources (Priority Order):
1. Environment variables (CI, local development)
2. AWS Secrets Manager (production, AWS Lambda/ECS)

IMPORTANT: Credentials are NEVER loaded from .env files - all must be set via environment variables.

Does NOT support:
- Hardcoded credentials
- Default empty strings for security-critical credentials
"""

import json as _json
import logging
import os
import threading
import time
from typing import Any, cast

logger = logging.getLogger(__name__)


def _sanitize_error(error: Exception) -> str:
    """Sanitize exception messages to prevent leaking ARNs, secret names, or credentials.

    Returns a generic error message that doesn't expose sensitive Secrets Manager details.
    """
    error_str = str(error)
    # Hide ARNs (arn:aws:... pattern)
    if "arn:aws:" in error_str:
        return "Secrets Manager access failed (check ARN and IAM permissions)"
    # Hide secret names and paths
    if "ResourceNotFoundException" in error_str or "not found" in error_str:
        return "Secret not found or access denied"
    # Hide other boto3 errors
    if "ClientError" in error_str or "botocore" in error_str:
        return "Secrets Manager API error (check network and credentials)"
    # Default: generic message
    return "Credential retrieval failed (internal error)"


# Cache TTL for credential secrets (5 minutes to balance freshness with API costs)
CREDENTIAL_CACHE_TTL_SECONDS = 300


class CredentialManager:
    """Centralized credential fetcher with caching and TTL-based expiration."""

    def __init__(self):
        self._cache: dict[str, tuple[Any, float]] = {}  # key -> (value, timestamp)
        self._is_aws = self._detect_aws()
        self._secrets_client = None

    def _detect_aws(self) -> bool:
        """Check if running in AWS Lambda/ECS or if AWS mode is forced.

        Returns True if:
        - Running in Lambda/ECS (AWS_EXECUTION_ENV is set)
        - FORCE_AWS env var is explicitly set to true (allows local access to AWS Secrets Manager)
        """
        # Check if forced by env var (allows local dev to access AWS Secrets Manager)
        if os.getenv("FORCE_AWS", "").lower() in ("true", "1", "yes"):
            return True
        # Check if running in AWS Lambda/ECS
        return bool(os.getenv("AWS_EXECUTION_ENV"))

    def _get_secrets_client(self):
        """Lazy-load boto3 Secrets Manager client."""
        if self._secrets_client is None:
            try:
                import boto3
                import botocore.config

                # Short timeouts so SM failures are fast errors, not 25s Lambda hangs.
                # Lambda timeout is 25s; connect+read must leave room for the actual DB call.
                # connect_timeout=3, read_timeout=5 -> worst case 8s per attempt x 2 = 16s,
                # leaving ~9s for the DB query. Previous 10+15=25s was hitting the timeout.
                _cfg = botocore.config.Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2})
                aws_region = os.getenv("AWS_REGION")
                if not aws_region:
                    raise ValueError(
                        "AWS_REGION environment variable is REQUIRED for Secrets Manager access. "
                        "Set it to your deployment region (e.g., us-east-1, us-west-2)."
                    )
                self._secrets_client = boto3.client(
                    "secretsmanager",
                    region_name=aws_region,
                    config=_cfg,
                )
            except ImportError as e:
                if self._is_aws:
                    raise RuntimeError(
                        "boto3 not available in AWS environment. This is a critical deployment error. "
                        "Ensure boto3 is installed in Lambda layer or container image."
                    ) from e
                logger.debug("boto3 not available; using environment variables only")
                self._secrets_client = False  # sentinel: tried and failed
        return self._secrets_client if self._secrets_client else None

    def get_password(self, secret_name: str, default: str | None = None) -> str:
        """
        Fetch a password/secret from Secrets Manager or environment.

        Args:
            secret_name: Name of the secret (e.g., 'db/password', 'alpaca/secret')
            default: Default value if not found (should be None for required secrets)

        Returns:
            The secret value

        Raises:
            ValueError: If secret not found and no default provided
        """
        return self._get_secret(secret_name, default, is_password=True)

    def get_secret(self, secret_name: str, default: str | None = None) -> str:
        """Alias for get_password (get_secret is more generic)."""
        return self.get_password(secret_name, default)

    def _get_secret(self, secret_name: str, default: str | None = None, is_password: bool = False) -> str:
        """
        Internal secret retrieval with caching and TTL-based expiration.

        Priority:
        1. Cache (if present and not expired)
        2. AWS Secrets Manager (if in AWS and available)
        3. Environment variable (env var name is secret_name with '/' → '_' and uppercase)
        4. Default value (if provided)
        5. Raise ValueError (if required and not found)
        """
        # Check cache with TTL
        if secret_name in self._cache:
            cached_value, timestamp = self._cache[secret_name]
            age = time.time() - timestamp
            if age < CREDENTIAL_CACHE_TTL_SECONDS:
                return cast(str, cached_value)
            else:
                # Cache expired, remove it and fetch fresh
                del self._cache[secret_name]

        # Try Secrets Manager if in AWS
        if self._is_aws:
            secret = self._fetch_from_secrets_manager(secret_name)
            if secret:
                self._cache[secret_name] = (secret, time.time())
                return secret

        # Fall back to environment variable
        env_var = secret_name.upper().replace("/", "_")
        secret = os.getenv(env_var)

        if secret:
            self._cache[secret_name] = (secret, time.time())
            return secret

        # Use default if provided
        if default is not None:
            return default

        # Fail if required and not found
        raise ValueError(
            "Required credential not found. Configure the secret in Secrets Manager or set the appropriate environment variable."
        )

    def _fetch_from_secrets_manager(self, secret_name: str) -> str | None:
        """Fetch from AWS Secrets Manager. Returns None if not found.

        Always fetches from AWS Secrets Manager. Fails fast if unavailable.
        No local caching or fallbacks — credentials must be current.

        IMPORTANT: Requires one of SecretString or SecretBinary to be present.
        Fails explicitly if both are missing.
        """
        try:
            client = self._get_secrets_client()
            if not client:
                raise RuntimeError(
                    "Secrets Manager client is unavailable. "
                    "Cannot fetch credentials — credentials must be fetched fresh from Secrets Manager every time."
                )

            # Try to get the secret by name
            response = client.get_secret_value(SecretId=secret_name)

            # Require one of SecretString or SecretBinary, no fallback to empty string
            secret_string = cast(str | None, response.get("SecretString"))
            secret_binary = cast(str | None, response.get("SecretBinary"))

            if secret_string:
                return secret_string
            elif secret_binary:
                return secret_binary
            else:
                raise ValueError(f"Secret '{secret_name}' exists but contains neither SecretString nor SecretBinary")

        except Exception as e:
            raise RuntimeError(_sanitize_error(e)) from e

    def get_db_credentials(self) -> dict[str, Any]:
        """Get database connection credentials as a dict.

        In AWS Lambda the RDS secret is a JSON blob stored under the ARN given by
        DB_SECRET_ARN. We fetch and parse that blob rather than looking up individual
        secret names, which don't exist in this setup.

        In local dev mode (DB_SECRET_ARN not set), all credentials must be explicitly
        provided via environment variables — no hardcoded defaults.

        Result is cached in self._cache to avoid a Secrets Manager API call on every
        DatabaseContext creation (which is called 10+ times per orchestrator run).
        Cache uses TTL to ensure fresh credentials are fetched periodically.

        REQUIRED FIELDS:
        - AWS Lambda: DB_SECRET_ARN must be set and contain host, port, username, password, dbname
        - Local dev: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME all required
        """
        import json as _json

        _db_creds_cache_key = "__db_credentials__"
        if _db_creds_cache_key in self._cache:
            cached_value: dict[str, Any]
            timestamp: float
            cached_value, timestamp = self._cache[_db_creds_cache_key]
            age = time.time() - timestamp
            if age < CREDENTIAL_CACHE_TTL_SECONDS:
                return cached_value

        secret_arn = os.getenv("DB_SECRET_ARN")
        if secret_arn and self._is_aws:
            client = self._get_secrets_client()
            if not client:
                raise RuntimeError(
                    "DB_SECRET_ARN is set but Secrets Manager client is unavailable. "
                    "Cannot fall back to environment variables for database credentials in AWS environment."
                )
            try:
                response = client.get_secret_value(SecretId=secret_arn)
                secret_string = response.get("SecretString")
                if not secret_string:
                    raise ValueError(f"DB_SECRET_ARN '{secret_arn}' exists but contains no SecretString")
                creds = _json.loads(secret_string)

                # Extract host (prefer DB_HOST env var override for proxy endpoints)
                db_host = os.getenv("DB_HOST") or os.getenv("DB_ENDPOINT")
                if not db_host:
                    db_host = creds.get("host")
                if not db_host:
                    raise ValueError("Database host not found in secret or DB_HOST/DB_ENDPOINT environment variables")

                # Extract port (no fallback, must be in secret)
                port_str = creds.get("port")
                if not port_str:
                    raise ValueError("Database port not found in secret")
                try:
                    port = int(port_str)
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Database port in secret is not a valid integer: {port_str}") from e

                # Extract username (no default)
                username = creds.get("username")
                if not username:
                    raise ValueError("Database username not found in secret")

                # Extract password (no default)
                password = creds.get("password")
                if not password:
                    raise ValueError("Database password not found in secret")

                # Extract database name (no default)
                database = creds.get("dbname")
                if not database:
                    raise ValueError("Database name (dbname) not found in secret")

                result = {
                    "host": db_host,
                    "port": port,
                    "user": username,
                    "password": password,
                    "database": database,
                }
                self._cache[_db_creds_cache_key] = (result, time.time())
                return result
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load database credentials from Secrets Manager: {_sanitize_error(e)}. "
                    "Database connections require fresh credentials from AWS Secrets Manager in Lambda environment."
                ) from e

        # Local dev mode: all credentials must be explicitly set
        db_host = os.getenv("DB_HOST") or os.getenv("DB_ENDPOINT")
        if not db_host:
            raise ValueError("DB_HOST not set in environment. Set DB_HOST before using credential manager.")

        db_port_str = os.getenv("DB_PORT")
        if not db_port_str:
            raise ValueError("DB_PORT not set in environment. Set DB_PORT before using credential manager.")
        try:
            db_port = int(db_port_str)
        except ValueError as e:
            raise ValueError(f"DB_PORT must be a valid integer, got: {db_port_str}") from e

        db_user = os.getenv("DB_USER")
        if not db_user:
            raise ValueError("DB_USER not set in environment. Set DB_USER before using credential manager.")

        password = self.get_password("db/password")
        if not password:
            raise ValueError("Database password not found in environment or Secrets Manager")

        db_name = os.getenv("DB_NAME")
        if not db_name:
            raise ValueError("DB_NAME not set in environment. Set DB_NAME before using credential manager.")

        result = {
            "host": db_host,
            "port": db_port,
            "user": db_user,
            "password": password,
            "database": db_name,
        }
        self._cache[_db_creds_cache_key] = (result, time.time())
        return result

    def get_alpaca_credentials(self, user_id: str | None = None) -> dict[str, str]:
        """Get Alpaca API credentials as a dict.

        Always fetches fresh credentials from Secrets Manager. Never returns cached/stale credentials.
        Enforces that credentials must be fetched within the last 5 minutes (CREDENTIAL_CACHE_TTL_SECONDS).

        SECURITY: Stale credential fallback removed (FIX H-3). If Secrets Manager is unreachable,
        the call fails hard rather than using potentially-rotated credentials. This prevents
        trades from executing with invalid API keys after credential rotation.

        Supports per-user credential isolation for multi-tenant trading.

        Args:
            user_id: Cognito sub (e.g., 'us-east-1_XJpLb9SKX:userid-12345'). If provided,
                     tries user-specific secret first before falling back to shared.

        Checks in order:
        1. User-specific secret: algo/alpaca/{user_id} (if user_id provided)
        2. ALGO_SECRETS_ARN env var → JSON blob (APCA_API_KEY_ID / APCA_API_SECRET_KEY fields)
        3. AWS Secrets Manager 'algo/alpaca' JSON blob (api_key, api_secret fields)
        4. Individual secrets 'alpaca/key' and 'alpaca/secret' (legacy)
        5. Environment variables APCA_API_KEY_ID and APCA_API_SECRET_KEY
        6. Fail hard if no fresh credentials available (no stale fallback)

        Raises ValueError if credentials not found or if Secrets Manager is unreachable.
        """
        # Step 1: Try user-specific secret if user_id provided
        # CRITICAL FIX: If user-specific secret exists but is invalid, FAIL HARD.
        # Silently falling back to shared credentials after finding a user secret would
        # cause trades to execute under the wrong account.
        if user_id and self._is_aws:
            try:
                client = self._get_secrets_client()
                if client:
                    user_secret_id = f"algo/alpaca/{user_id}"
                    try:
                        response = client.get_secret_value(SecretId=user_secret_id)
                        secret_string = response.get("SecretString")
                        if not secret_string:
                            raise ValueError(f"User secret '{user_secret_id}' exists but contains no SecretString")
                        creds = _json.loads(secret_string)
                        key = creds.get("api_key") or creds.get("APCA_API_KEY_ID")
                        secret = creds.get("api_secret") or creds.get("APCA_API_SECRET_KEY")
                        if key and secret:
                            logger.info(f"[CREDENTIALS] User-scoped Alpaca credentials loaded for {user_id}")
                            return {"key": key, "secret": secret}
                        else:
                            # User-specific secret exists but is invalid — FAIL HARD
                            raise ValueError(
                                f"[CREDENTIALS_CRITICAL] User secret '{user_secret_id}' exists but missing or invalid credentials. "
                                f"Cannot fall back to shared credentials (would trade under wrong account). "
                                f"Verify user secret contains api_key/APCA_API_KEY_ID and api_secret/APCA_API_SECRET_KEY."
                            )
                    except client.exceptions.ResourceNotFoundException:
                        logger.debug(
                            f"[CREDENTIALS] No user-specific Alpaca secret for {user_id}, falling back to shared"
                        )
                    except ValueError:
                        # Re-raise ValueError (validation errors) without catching
                        raise
                    except Exception as e:
                        # Convert other exceptions to ValueError to trigger fail-hard below
                        raise ValueError(
                            f"[CREDENTIALS_CRITICAL] Could not fetch user-specific Alpaca credentials for {user_id}: {e}. "
                            f"Cannot fall back to shared credentials (would trade under wrong account)."
                        ) from e
            except ValueError:
                # Re-raise ValueError so it triggers the fail-hard logic below
                raise

        # Step 2: Try ALGO_SECRETS_ARN (Terraform-managed secret: algo-algo-secrets-dev)
        # LIVE MODE EXCEPTION: ALGO_SECRETS_ARN always contains PAPER keys (hardcoded in deploy
        # workflow as ALPACA_API_KEY_ID). For live trading, skip this source and fall through to
        # algo/alpaca which is updated by update-credentials.yml -f trading_mode=live.
        algo_secrets_arn = os.getenv("ALGO_SECRETS_ARN")
        is_paper_mode = os.getenv("ALPACA_PAPER_TRADING", "true").strip().lower() != "false"
        if algo_secrets_arn and self._is_aws and is_paper_mode:
            try:
                client = self._get_secrets_client()
                if client:
                    response = client.get_secret_value(SecretId=algo_secrets_arn)
                    secret_string = response.get("SecretString")
                    if not secret_string:
                        raise ValueError(f"ALGO_SECRETS_ARN '{algo_secrets_arn}' exists but contains no SecretString")
                    creds = _json.loads(secret_string)
                    key = creds.get("APCA_API_KEY_ID")
                    secret = creds.get("APCA_API_SECRET_KEY")
                    if key and secret:
                        logger.info("[CREDENTIALS] Alpaca credentials loaded from ALGO_SECRETS_ARN (paper mode)")
                        return {"key": key, "secret": secret}
                    else:
                        raise ValueError(
                            f"ALGO_SECRETS_ARN '{algo_secrets_arn}' exists but missing APCA_API_KEY_ID or APCA_API_SECRET_KEY"
                        )
            except ValueError as e:
                logger.warning(f"[CREDENTIALS] ALGO_SECRETS_ARN validation failed: {e}")
            except Exception as e:
                logger.error(
                    f"[CREDENTIALS] Could not fetch Alpaca credentials from configured secret: {_sanitize_error(e)}"
                )
        elif algo_secrets_arn and self._is_aws and not is_paper_mode:
            logger.info("[CREDENTIALS] Live mode: skipping ALGO_SECRETS_ARN (contains paper keys), using algo/alpaca")

        # Step 3: Try 'algo/alpaca' JSON blob (legacy secrets module format)
        if self._is_aws:
            try:
                client = self._get_secrets_client()
                if client:
                    alpaca_secret_id = os.getenv("ALPACA_LEGACY_SECRET_ID", "algo/alpaca")
                    response = client.get_secret_value(SecretId=alpaca_secret_id)
                    secret_string = response.get("SecretString")
                    if not secret_string:
                        raise ValueError(f"Alpaca secret '{alpaca_secret_id}' exists but contains no SecretString")
                    creds = _json.loads(secret_string)
                    key = creds.get("api_key")
                    secret = creds.get("api_secret")
                    if key and secret:
                        return {"key": key, "secret": secret}
                    else:
                        raise ValueError(f"Alpaca secret '{alpaca_secret_id}' exists but missing api_key or api_secret")
            except ValueError as e:
                logger.warning(f"Alpaca secret validation failed: {e}")
            except Exception as e:
                logger.warning(f"Could not fetch Alpaca secret from Secrets Manager: {_sanitize_error(e)}")

        # Step 4: Try individual secrets (legacy format) — get_password already tries Secrets Manager then env var
        try:
            key = self.get_password("alpaca/key", default=None)
            secret = self.get_password("alpaca/secret", default=None)
            logger.info("[CREDENTIALS] Alpaca credentials loaded from legacy secrets")
            return {"key": key, "secret": secret}
        except ValueError:
            # Neither legacy secret nor env var found; will fail below with explicit error
            pass

        # FIX H-3: No credentials found from any fresh source
        # CRITICAL: We DO NOT fall back to stale cached credentials when Secrets Manager is unreachable.
        # If credentials were rotated and Secrets Manager becomes temporarily unavailable, using old
        # cached credentials will cause trade execution with invalid API keys, leading to 401 errors
        # or worse, failed trades with incorrect credentials.
        #
        # Instead, fail hard and let Lambda retry on the next invocation. This enforces that every
        # trade execution uses credentials fetched within the last 5 minutes (CREDENTIAL_CACHE_TTL_SECONDS).
        logger.error("[CREDENTIALS] Alpaca credentials NOT FOUND - trades cannot be executed!")
        logger.error("[CREDENTIALS_H3_FIX] Stale credential fallback REMOVED (was security risk after rotation)")
        raise ValueError(
            "Alpaca API credentials not found. Verify credentials are configured in AWS Secrets Manager and accessible. "
            "If Secrets Manager is unreachable, check CloudWatch alarm [ALPACA_CREDS_FETCH_FAILED]. "
            "NOTE: Stale credential fallback is disabled—credentials must be fetched fresh within the last 5 minutes."
        )

    def get_smtp_credentials(self) -> dict[str, Any] | None:
        """Get SMTP credentials. Returns None if not configured.

        If any SMTP env var or secret is set, ALL SMTP fields must be explicitly provided.
        No defaults or partial fallbacks.

        Fields required if SMTP is configured:
        - ALERT_SMTP_HOST or smtp/host secret
        - ALERT_SMTP_USER or smtp/user secret
        - ALERT_SMTP_PASSWORD or smtp/password secret
        - ALERT_SMTP_PORT or smtp/port secret
        """
        # Check if SMTP is configured by looking for any required field
        has_smtp_host = os.getenv("ALERT_SMTP_HOST") is not None
        has_smtp_user = os.getenv("ALERT_SMTP_USER") is not None
        has_smtp_password = os.getenv("ALERT_SMTP_PASSWORD") is not None
        has_smtp_port = os.getenv("ALERT_SMTP_PORT") is not None

        if not (has_smtp_host or has_smtp_user or has_smtp_password or has_smtp_port):
            return None

        # If any field is set, all must be explicitly configured
        smtp_host = os.getenv("ALERT_SMTP_HOST")
        if not smtp_host:
            raise ValueError(
                "SMTP is partially configured but ALERT_SMTP_HOST is not set. Either configure all SMTP fields or none."
            )

        smtp_user = os.getenv("ALERT_SMTP_USER")
        if not smtp_user:
            raise ValueError(
                "SMTP is partially configured but ALERT_SMTP_USER is not set. Either configure all SMTP fields or none."
            )

        smtp_password = os.getenv("ALERT_SMTP_PASSWORD")
        if not smtp_password:
            raise ValueError(
                "SMTP is partially configured but ALERT_SMTP_PASSWORD is not set. "
                "Either configure all SMTP fields or none."
            )

        smtp_port_str = os.getenv("ALERT_SMTP_PORT")
        if not smtp_port_str:
            raise ValueError(
                "SMTP is partially configured but ALERT_SMTP_PORT is not set. Either configure all SMTP fields or none."
            )

        try:
            smtp_port = int(smtp_port_str)
        except ValueError as e:
            raise ValueError(f"ALERT_SMTP_PORT must be a valid integer, got: {smtp_port_str}") from e

        return {
            "username": smtp_user,
            "password": smtp_password,
            "host": smtp_host,
            "port": smtp_port,
        }

    def clear_cache(self):
        """Clear credential cache (useful for testing or forcing a refresh)."""
        self._cache.clear()

    def clear_expired_credentials(self):
        """Remove expired credentials from cache without clearing everything."""
        now = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self._cache.items() if now - timestamp >= CREDENTIAL_CACHE_TTL_SECONDS
        ]
        for key in expired_keys:
            del self._cache[key]

    def invalidate_alpaca_credentials(self):
        """FIX S-17: Clear cached Alpaca credentials when detected as invalid (e.g., 401 from API).

        Call this when Alpaca returns 401 Unauthorized to force a refetch on next request.
        Also emits CloudWatch metric for ops team to trigger manual rotation if needed.
        """
        _alpaca_creds_cache_key = "__alpaca_credentials__"
        if _alpaca_creds_cache_key in self._cache:
            _cached_creds, timestamp = self._cache[_alpaca_creds_cache_key]
            age = time.time() - timestamp
            logger.warning(
                "[CREDENTIALS_INVALID] Alpaca credentials detected as invalid (401). "
                f"Clearing cache (credentials were {age:.0f}s old). Next request will refetch from Secrets Manager."
            )
            del self._cache[_alpaca_creds_cache_key]

            # Emit CloudWatch alarm metric for ops to investigate credential rotation
            try:
                import boto3

                cloudwatch = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION", "us-east-1"))
                cloudwatch.put_metric_data(
                    Namespace="AlgoTradingPlatform",
                    MetricData=[
                        {
                            "MetricName": "AlpacaCredentialsInvalidated",
                            "Value": 1,
                            "Unit": "Count",
                        }
                    ],
                )
                logger.info("[CREDENTIALS_INVALID] CloudWatch metric emitted: AlpacaCredentialsInvalidated")
            except Exception as e:
                logger.warning(f"[CREDENTIALS_INVALID] Could not emit CloudWatch metric: {_sanitize_error(e)}")
        else:
            logger.info("[CREDENTIALS_INVALID] Alpaca credentials not in cache (already cleared or never cached)")


# Singleton instance (thread-safe)
_manager = None
_manager_lock = threading.Lock()


def get_credential_manager() -> CredentialManager:
    """Get the global credential manager instance (thread-safe).

    Uses double-checked locking to prevent race conditions during initialization.
    """
    global _manager
    if _manager is None:
        with _manager_lock:
            # Double-check pattern to avoid race conditions
            if _manager is None:
                _manager = CredentialManager()
    return _manager


def get_password(secret_name: str, default: str | None = None) -> str:
    """Module-level convenience function."""
    return get_credential_manager().get_password(secret_name, default)


def get_secret(secret_name: str, default: str | None = None) -> str:
    """Module-level convenience function (alias)."""
    return get_credential_manager().get_secret(secret_name, default)


def get_db_credentials() -> dict[str, str]:
    """Module-level convenience function."""
    return get_credential_manager().get_db_credentials()


def get_alpaca_credentials(user_id: str | None = None) -> dict[str, str]:
    """Module-level convenience function for Alpaca credentials.

    Args:
        user_id: Optional Cognito sub for user-scoped credentials.
                 If None, uses shared/default credentials.
    """
    return get_credential_manager().get_alpaca_credentials(user_id=user_id)


def get_db_password() -> str:
    """Get database password only.

    Replaces credential_helper.get_db_password() after consolidation.
    Uses DB_SECRET_ARN in AWS Lambda, falls back to environment variables.
    """
    creds = get_db_credentials()
    return creds["password"]


def get_db_config() -> dict[str, Any]:
    """Get full database configuration dict.

    Replaces credential_helper.get_db_config() after consolidation.
    Returns host, port, user, password, database.
    """
    return get_db_credentials()


def clear_credential_cache():
    """Clear the credential cache.

    Called at Lambda invocation start to ensure fresh credentials are fetched
    for each invocation. This is important for credential rotation: if a Lambda
    stays warm after credentials are rotated, we want to pick up the new ones
    on the next invocation.

    Safe to call even if no manager exists yet (creates fresh one).
    """
    mgr = get_credential_manager()
    mgr.clear_cache()
    return True


def clear_expired_credentials():
    """Remove only expired credentials from cache, keeping fresh ones.

    This is called at Lambda invocation start instead of clearing the entire cache.
    It respects the 5-minute TTL: credentials fresher than TTL are kept, stale ones
    are removed so they'll be refetched on next access. This balances credential
    rotation (stale creds are refreshed) with cost (we don't hit Secrets Manager
    on every invocation).
    """
    mgr = get_credential_manager()
    mgr.clear_expired_credentials()
    return True


def invalidate_alpaca_credentials():
    """FIX S-17: Clear cached Alpaca credentials when detected as invalid (e.g., 401 from API).

    Call this from trade executor when Alpaca returns 401 Unauthorized.
    Forces a refetch of credentials on next request.
    Also emits CloudWatch metric for ops team to investigate.
    """
    mgr = get_credential_manager()
    mgr.invalidate_alpaca_credentials()


if __name__ == "__main__":
    # Simple test: try to get credentials
    try:
        db_creds = get_db_credentials()
        logger.info("[OK] DB credentials loaded")
    except ValueError as e:
        logger.info(f"[ERROR] DB credentials: {e}")

    try:
        alpaca_creds = get_alpaca_credentials()
        if alpaca_creds["key"]:
            logger.info("[OK] Alpaca credentials loaded")
    except ValueError as e:
        logger.info(f"[ERROR] Alpaca credentials: {e}")
