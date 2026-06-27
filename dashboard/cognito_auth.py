"""Cognito authentication for AWS API access.

Handles dynamic token lifecycle: authentication, refresh, caching, and expiry.
"""

import binascii
import json
import logging
import os
import platform
import sys
import time
from datetime import datetime
from typing import cast

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class CognitoAuth:
    """Handle Cognito authentication and token lifecycle."""

    def __init__(self, user_pool_id: str, client_id: str, region: str = "us-east-1"):
        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.region = region
        self.cognito_client = boto3.client("cognito-idp", region_name=region)
        self.access_token: str | None = None
        self.id_token: str | None = None
        self.refresh_token: str | None = None
        self.token_expires_at: float | None = None
        self.username: str | None = None
        self._auth_lost_time: float | None = None

    def _parse_jwt_expiry(self, token: str) -> float | None:
        """Parse JWT expiry time. Returns Unix timestamp or raises RuntimeError if invalid."""
        try:
            import base64

            parts = token.split(".")
            if len(parts) != 3:
                raise RuntimeError("JWT must have exactly 3 parts (header.payload.signature)")
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
            exp = payload.get("exp")
            if exp is None:
                raise RuntimeError("JWT payload missing 'exp' claim")
            return cast(float, exp)
        except (ValueError, TypeError, RuntimeError) as e:
            raise RuntimeError(f"Failed to parse JWT expiry: {e}") from e

    def authenticate(self, username: str, password: str) -> bool:
        """Authenticate user with Cognito. Returns True if successful."""
        try:
            response = self.cognito_client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": username, "PASSWORD": password},
            )
            auth_result = response.get("AuthenticationResult")
            self.access_token = auth_result.get("AccessToken")
            self.id_token = auth_result.get("IdToken")
            self.refresh_token = auth_result.get("RefreshToken")
            self.username = username
            if self.access_token:
                self.token_expires_at = self._parse_jwt_expiry(self.access_token)
            return bool(self.access_token)
        except ClientError as e:
            error_dict = e.response.get("Error", {})
            if not error_dict:
                logger.error(f"[COGNITO] ClientError with malformed response (missing 'Error' dict): {e.response}")
                return False
            error_code = error_dict.get("Code")
            if error_code == "NotAuthorizedException":
                logger.error(f"Invalid credentials for user: {username}")
            elif error_code == "UserNotFoundException":
                logger.error(f"User not found: {username}")
            else:
                logger.error(f"Authentication error: {e}")
            return False
        except RuntimeError as e:
            logger.error(f"JWT parsing failed during authentication: {e}")
            return False

    def refresh_access_token(self) -> bool:
        """Refresh the access token. Returns True if successful."""
        if not self.refresh_token:
            return False
        try:
            response = self.cognito_client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters={"REFRESH_TOKEN": self.refresh_token},
            )
            auth_result = response.get("AuthenticationResult")
            self.access_token = auth_result.get("AccessToken")
            self.id_token = auth_result.get("IdToken")
            if self.access_token:
                self.token_expires_at = self._parse_jwt_expiry(self.access_token)
            return bool(self.access_token)
        except ClientError as e:
            logger.error(f"Token refresh failed: {e}")
            return False
        except RuntimeError as e:
            logger.error(f"JWT parsing failed during token refresh: {e}")
            return False

    def is_token_expired(self) -> bool:
        """Check if access token is expired or about to expire (5 min buffer)."""
        if not self.token_expires_at:
            return True
        now = time.time()
        buffer = 300  # 5 minute buffer
        return now > (self.token_expires_at - buffer)

    def get_authorization_header(self) -> dict[str, str]:
        """Get Authorization header, refreshing if needed. Validates token format before returning.

        Raises RuntimeError if no token available or token is invalid/expired.
        Fail-fast: Never returns empty dict for missing token.
        """
        if not self.access_token:
            raise RuntimeError(
                "Authorization header not available: no access token. "
                "Dashboard requires authentication - user must re-authenticate via Cognito."
            )

        if self.is_token_expired():
            if not self.refresh_token:
                msg = "Token expired and no refresh token available - authentication lost (must re-authenticate)"
                logger.error(msg)
                self._auth_lost_time = time.time()
                raise RuntimeError(msg)
            if not self.refresh_access_token():
                msg = "Token refresh failed - authentication lost (must re-authenticate)"
                logger.error(msg)
                self._auth_lost_time = time.time()
                raise RuntimeError(msg)

        if not self.access_token:
            msg = "Authorization header validation failed: no access token available"
            logger.error(msg)
            raise RuntimeError(msg)

        try:
            self._is_valid_jwt(self.access_token)
        except RuntimeError as e:
            msg = f"Authorization header validation failed: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e

        return {"Authorization": f"Bearer {self.access_token}"}

    def _is_valid_jwt(self, token: str) -> bool:
        """Check if token is a valid JWT with required claims (exp, sub) and proper structure.

        Raises RuntimeError if validation fails (fail-fast for auth integrity).
        """
        try:
            import base64

            parts = token.split(".")
            if len(parts) != 3:
                raise RuntimeError(f"JWT must have exactly 3 parts, got {len(parts)}")

            # All parts must be non-empty
            if not all(part for part in parts):
                raise RuntimeError("JWT contains empty parts")

            # Validate header is valid base64
            try:
                base64.urlsafe_b64decode(parts[0] + "==")
            except binascii.Error as e:
                raise RuntimeError(f"JWT header is not valid base64: {e}") from e

            # Validate payload is valid base64 and contains required claims
            try:
                payload_json = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
            except (binascii.Error, json.JSONDecodeError) as e:
                raise RuntimeError(f"JWT payload is not valid base64 or JSON: {e}") from e

            if "exp" not in payload_json or "sub" not in payload_json:
                raise RuntimeError(f"JWT payload missing required claims: exp={('exp' in payload_json)}, sub={('sub' in payload_json)}")

            # Validate signature is present and valid base64
            try:
                base64.urlsafe_b64decode(parts[2] + "==")
            except binascii.Error as e:
                raise RuntimeError(f"JWT signature is not valid base64: {e}") from e

            return True
        except RuntimeError:
            raise

    def is_authenticated(self) -> bool:
        """Check if user has valid credentials."""
        return bool(self.access_token) and not self.is_token_expired()

    def has_lost_authentication(self) -> bool:
        """Check if authentication was recently lost due to token failure."""
        return self._auth_lost_time is not None


def _get_or_create_test_user() -> tuple[str | None, str | None]:
    """Try to get test user credentials from various sources."""
    # Try environment variables
    username = os.environ.get("COGNITO_TEST_USER_EMAIL")
    password = os.environ.get("COGNITO_TEST_USER_PASSWORD")
    if username and password:
        return username, password

    # Try loading from cache
    token_file = os.path.expanduser("~/.algo/cognito_credentials.json")
    if os.path.exists(token_file):
        try:
            with open(token_file) as f:
                creds = json.load(f)
                if "username" not in creds or "password" not in creds:
                    raise ValueError(
                        f"[COGNITO] Credentials file missing required fields. "
                        f"Available: {list(creds.keys()) if isinstance(creds, dict) else 'not a dict'}. "
                        f"File corrupted; delete and re-authenticate."
                    )
                return creds["username"], creds["password"]
        except Exception as cred_err:
            logger.debug(f"Could not load cached credentials: {cred_err}")

    # Return None to signal no cached credentials available (user will be prompted)
    return None, None


def _get_aws_cfn_output(key: str) -> str | None:
    """Try to get Cognito credentials from AWS CloudFormation stack outputs."""
    try:
        cfn_client = boto3.client("cloudformation", region_name="us-east-1")
        stacks = cfn_client.list_stacks(StackStatusFilter=["CREATE_COMPLETE", "UPDATE_COMPLETE"])
        stack_summaries = stacks.get("StackSummaries")

        if not stack_summaries:
            return None

        for stack in stack_summaries:
            if "algo" in stack["StackName"].lower():
                response = cfn_client.describe_stacks(StackName=stack["StackName"])
                outputs = response["Stacks"][0].get("Outputs")

                if not outputs:
                    continue

                for output in outputs:
                    if output["OutputKey"] == key:
                        return cast(str, output["OutputValue"])
    except Exception as e:
        raise RuntimeError(f"Operation failed: {e}") from e
    return None


def get_cognito_auth(require_auth: bool = True, interactive: bool = True) -> CognitoAuth | None:  # noqa: C901
    """
    Dynamically get authenticated Cognito instance.

    Tries (in order):
    1. COGNITO_USERNAME + COGNITO_PASSWORD env vars
    2. Cached token from ~/.algo/cognito_token.json
    3. Secrets Manager: algo/dashboard-config (cognito_username + cognito_password)
    4. Saved credentials from ~/.algo/cognito_credentials.json
    5. Interactive prompt (if interactive=True and TTY available)

    Returns authenticated CognitoAuth or None if all methods fail.
    """
    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    client_id = os.environ.get("COGNITO_CLIENT_ID")

    if not (user_pool_id and client_id):
        if require_auth:
            msg = (
                "Cognito not configured — missing COGNITO_USER_POOL_ID or COGNITO_CLIENT_ID env vars. "
                "Dashboard requires authentication. "
                "Run: scripts/setup-local-dev.ps1 or set env vars and try again."
            )
            logger.error(f"[Cognito] {msg}")
            raise RuntimeError(msg)
        logger.debug("Cognito not configured (COGNITO_USER_POOL_ID or COGNITO_CLIENT_ID missing)")
        return None

    auth = CognitoAuth(user_pool_id, client_id)

    if not require_auth:
        return auth

    # 1. Try environment variables
    username = os.environ.get("COGNITO_USERNAME")
    password = os.environ.get("COGNITO_PASSWORD")
    if username and password:
        if auth.authenticate(username, password):
            logger.info(f"[Cognito] Authenticated as {username}")
            return auth
        else:
            logger.warning(f"[Cognito] Failed to authenticate {username} from env vars")
            return None

    # 2. Try cached token
    token_file = os.path.expanduser("~/.algo/cognito_token.json")
    if os.path.exists(token_file):
        try:
            # Verify file permissions are restrictive (owner read/write only)
            # Only enforce on Unix-like systems; Windows NTFS doesn't use these permission bits
            should_remove = False
            if platform.system() != "Windows":
                file_stat = os.stat(token_file)
                file_mode = file_stat.st_mode & 0o777
                if file_mode != 0o600:
                    logger.warning(f"[Cognito] Token file has overly permissive mode {oct(file_mode)}, removing")
                    should_remove = True

            if should_remove:
                os.remove(token_file)
            else:
                with open(token_file) as f:
                    tokens = json.load(f)
                    auth.access_token = tokens.get("access_token")
                    auth.refresh_token = tokens.get("refresh_token")
                    auth.id_token = tokens.get("id_token")
                    auth.username = tokens.get("username")
                    auth.token_expires_at = tokens.get("expires_at")

                    if auth.is_authenticated():
                        logger.info(f"[Cognito] Loaded cached token for {auth.username}")
                        return auth
                    elif auth.refresh_token and auth.refresh_access_token():
                        logger.info(f"[Cognito] Refreshed expired token for {auth.username}")
                        return auth
                    else:
                        os.remove(token_file)
                        logger.debug("[Cognito] Cached token invalid, removed")
        except Exception as e:
            logger.warning(f"[Cognito] Failed to load cached token: {e}")

    # 3. Try credentials from Secrets Manager (algo/dashboard-config)
    try:
        sm = boto3.client("secretsmanager", region_name="us-east-1")
        secret_resp = sm.get_secret_value(SecretId="algo/dashboard-config")
        secret_data = json.loads(secret_resp["SecretString"])
        sm_user = secret_data.get("cognito_username")
        sm_pass = secret_data.get("cognito_password")
        if sm_user and sm_pass:
            if auth.authenticate(sm_user, sm_pass):
                logger.info(f"[Cognito] Authenticated from Secrets Manager: {sm_user}")
                return auth
            else:
                logger.debug(f"[Cognito] Secrets Manager credentials invalid for {sm_user}")
    except Exception as e:
        logger.debug(f"[Cognito] Could not read from Secrets Manager: {e}")

    # 4. Try credentials from saved file (non-interactive fallback)
    saved_user, saved_pass = _get_or_create_test_user()
    if saved_user and saved_pass:
        if auth.authenticate(saved_user, saved_pass):
            logger.info(f"[Cognito] Authenticated from saved credentials file: {saved_user}")
            return auth
        else:
            logger.debug(f"[Cognito] Saved credentials invalid for {saved_user}")

    # 5. Try interactive authentication
    if interactive and sys.stdin.isatty():
        try:
            print("\n" + "=" * 60)
            print("Cognito Authentication Required")
            print("=" * 60)
            print("Set COGNITO_USERNAME + COGNITO_PASSWORD env vars to skip this prompt.")
            username = input(f"Email [{saved_user}]: ").strip() or saved_user
            password = input("Password: ").strip()
            # Type guard: ensure username and password are strings before authenticating
            if username and password:
                if auth.authenticate(username, password):
                    logger.info(f"[Cognito] Authenticated as {username}")
                    return auth
                else:
                    print("[ERROR] Authentication failed")
                    return None
            else:
                print("[ERROR] Username or password missing")
                return None
        except (KeyboardInterrupt, EOFError):
            logger.info("[Cognito] Authentication cancelled")
            return None

    # 6. All auth methods failed
    if require_auth:
        msg = (
            "No credentials available — run deploy workflow to provision credentials in Secrets Manager, "
            "or set COGNITO_USERNAME + COGNITO_PASSWORD environment variables"
        )
        logger.error(f"[Cognito] Authentication required but failed: {msg}")
        raise RuntimeError(msg)

    # If require_auth=False, return unauthenticated instance for optional auth scenarios
    logger.warning(
        "[Cognito] No credentials available — run deploy workflow to provision credentials in Secrets Manager"
    )
    return auth


def save_tokens(auth: CognitoAuth) -> None:
    """Save tokens and credentials for future use with restricted file permissions."""
    if not auth.is_authenticated():
        return
    token_file = os.path.expanduser("~/.algo/cognito_token.json")
    token_dir = os.path.dirname(token_file)
    os.makedirs(token_dir, exist_ok=True)

    tokens = {
        "access_token": auth.access_token,
        "refresh_token": auth.refresh_token,
        "id_token": auth.id_token,
        "username": auth.username,
        "expires_at": auth.token_expires_at,
        "saved_at": datetime.utcnow().isoformat(),
    }
    with open(token_file, "w") as f:
        json.dump(tokens, f)

    # Set restrictive file permissions (owner read/write only)
    try:
        os.chmod(token_file, 0o600)
    except OSError as e:
        logger.warning(f"[Cognito] Failed to set token file permissions: {e}")

    logger.debug(f"[Cognito] Saved tokens for {auth.username}")
