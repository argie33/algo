"""Cognito authentication for AWS API access.

Handles dynamic token lifecycle: authentication, refresh, caching, and expiry.
"""

import json
import logging
import os
import sys
import time
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
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
        self.access_token: Optional[str] = None
        self.id_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires_at: Optional[float] = None
        self.username: Optional[str] = None

    def _parse_jwt_expiry(self, token: str) -> Optional[float]:
        """Parse JWT expiry time. Returns Unix timestamp or None if invalid."""
        try:
            import base64
            parts = token.split('.')
            if len(parts) != 3:
                return None
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
            return payload.get('exp')
        except Exception:
            return None

    def authenticate(self, username: str, password: str) -> bool:
        """Authenticate user with Cognito. Returns True if successful."""
        try:
            response = self.cognito_client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": username, "PASSWORD": password}
            )
            auth_result = response.get("AuthenticationResult", {})
            self.access_token = auth_result.get("AccessToken")
            self.id_token = auth_result.get("IdToken")
            self.refresh_token = auth_result.get("RefreshToken")
            self.username = username
            self.token_expires_at = self._parse_jwt_expiry(self.access_token) if self.access_token else None
            return bool(self.access_token)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "NotAuthorizedException":
                logger.error(f"Invalid credentials for user: {username}")
            elif error_code == "UserNotFoundException":
                logger.error(f"User not found: {username}")
            else:
                logger.error(f"Authentication error: {e}")
            return False

    def refresh_access_token(self) -> bool:
        """Refresh the access token. Returns True if successful."""
        if not self.refresh_token:
            return False
        try:
            response = self.cognito_client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters={"REFRESH_TOKEN": self.refresh_token}
            )
            auth_result = response.get("AuthenticationResult", {})
            self.access_token = auth_result.get("AccessToken")
            self.id_token = auth_result.get("IdToken")
            self.token_expires_at = self._parse_jwt_expiry(self.access_token) if self.access_token else None
            return bool(self.access_token)
        except ClientError as e:
            logger.error(f"Token refresh failed: {e}")
            return False

    def is_token_expired(self) -> bool:
        """Check if access token is expired or about to expire (5 min buffer)."""
        if not self.token_expires_at:
            return True
        now = time.time()
        buffer = 300  # 5 minute buffer
        return now > (self.token_expires_at - buffer)

    def get_authorization_header(self) -> Dict[str, str]:
        """Get Authorization header, refreshing if needed."""
        if not self.access_token:
            return {}
        if self.is_token_expired() and self.refresh_token:
            self.refresh_access_token()
        return {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}

    def is_authenticated(self) -> bool:
        """Check if user has valid credentials."""
        return bool(self.access_token) and not self.is_token_expired()


def _get_or_create_test_user() -> Tuple[str, str]:
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
            with open(token_file, "r") as f:
                creds = json.load(f)
                return creds.get("username", ""), creds.get("password", "")
        except Exception as cred_err:
            import logging
            logging.debug(f"Could not load cached credentials: {cred_err}")

    # Return empty defaults (user will be prompted for real values)
    return "", ""


def _get_aws_cfn_output(key: str) -> Optional[str]:
    """Try to get Cognito credentials from AWS CloudFormation stack outputs."""
    try:
        cfn_client = boto3.client('cloudformation', region_name='us-east-1')
        stacks = cfn_client.list_stacks(StackStatusFilter=['CREATE_COMPLETE', 'UPDATE_COMPLETE'])
        for stack in stacks.get('StackSummaries', []):
            if 'algo' in stack['StackName'].lower():
                response = cfn_client.describe_stacks(StackName=stack['StackName'])
                outputs = response['Stacks'][0].get('Outputs', [])
                for output in outputs:
                    if output['OutputKey'] == key:
                        return output['OutputValue']
    except Exception as e:
        logger.debug(f"Failed to get CFN output: {e}")
    return None


def get_cognito_auth(require_auth: bool = True, interactive: bool = True) -> Optional[CognitoAuth]:
    """
    Dynamically get authenticated Cognito instance.

    Tries (in order):
    1. COGNITO_USERNAME + COGNITO_PASSWORD env vars
    2. Cached token from ~/.algo/cognito_token.json
    3. Interactive prompt (if interactive=True)
    4. AWS CloudFormation outputs as fallback

    Returns authenticated CognitoAuth or None if all methods fail.
    """
    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    client_id = os.environ.get("COGNITO_CLIENT_ID")

    if not (user_pool_id and client_id):
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
            file_stat = os.stat(token_file)
            file_mode = file_stat.st_mode & 0o777
            if file_mode != 0o600:
                logger.warning(f"[Cognito] Token file has overly permissive mode {oct(file_mode)}, removing")
                os.remove(token_file)
            else:
                with open(token_file, "r") as f:
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

    # 3. Try credentials from saved file (non-interactive fallback)
    saved_user, saved_pass = _get_or_create_test_user()
    if saved_user and saved_pass:
        if auth.authenticate(saved_user, saved_pass):
            logger.info(f"[Cognito] Authenticated from saved credentials file: {saved_user}")
            return auth
        else:
            logger.debug(f"[Cognito] Saved credentials invalid for {saved_user}")

    # 4. Try interactive authentication
    if interactive and sys.stdin.isatty():
        try:
            print("\n" + "="*60)
            print("Cognito Authentication Required")
            print("="*60)
            print(f"Set COGNITO_USERNAME + COGNITO_PASSWORD env vars to skip this prompt.")
            username = input(f"Email [{saved_user}]: ").strip() or saved_user
            password = input("Password: ").strip()
            if auth.authenticate(username, password):
                logger.info(f"[Cognito] Authenticated as {username}")
                return auth
            else:
                print("[ERROR] Authentication failed")
                return None
        except (KeyboardInterrupt, EOFError):
            logger.info("[Cognito] Authentication cancelled")
            return None

    # 5. Fallback: return unauthenticated instance (will fail on protected endpoints)
    logger.warning("[Cognito] No credentials available - set COGNITO_USERNAME + COGNITO_PASSWORD env vars or run from a terminal")
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
        "saved_at": datetime.utcnow().isoformat()
    }
    with open(token_file, "w") as f:
        json.dump(tokens, f)

    # Set restrictive file permissions (owner read/write only)
    try:
        os.chmod(token_file, 0o600)
    except OSError as e:
        logger.warning(f"[Cognito] Failed to set token file permissions: {e}")

    logger.debug(f"[Cognito] Saved tokens for {auth.username}")
