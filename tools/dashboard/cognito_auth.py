"""Cognito authentication for AWS API access."""

import json
import os
from typing import Optional, Dict
import boto3
from botocore.exceptions import ClientError

class CognitoAuth:
    """Handle Cognito authentication and token management."""

    def __init__(self, user_pool_id: str, client_id: str, region: str = "us-east-1"):
        """
        Initialize Cognito authentication.

        Args:
            user_pool_id: Cognito User Pool ID (e.g., us-east-1_xxxxxxxxx)
            client_id: Cognito App Client ID
            region: AWS region
        """
        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.region = region
        self.cognito_client = boto3.client("cognito-idp", region_name=region)
        self.access_token: Optional[str] = None
        self.id_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    def authenticate(self, username: str, password: str) -> bool:
        """
        Authenticate user with Cognito using username and password.

        Args:
            username: Cognito username (usually email)
            password: Cognito password

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            response = self.cognito_client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={
                    "USERNAME": username,
                    "PASSWORD": password,
                }
            )

            # Extract tokens from authentication result
            auth_result = response.get("AuthenticationResult", {})
            self.access_token = auth_result.get("AccessToken")
            self.id_token = auth_result.get("IdToken")
            self.refresh_token = auth_result.get("RefreshToken")

            if self.access_token:
                return True
            return False

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "NotAuthorizedException":
                print("Invalid username or password")
            elif error_code == "UserNotFoundException":
                print("User not found")
            else:
                print(f"Authentication error: {e}")
            return False

    def refresh_access_token(self) -> bool:
        """
        Refresh the access token using the refresh token.

        Returns:
            True if refresh successful, False otherwise
        """
        if not self.refresh_token:
            return False

        try:
            response = self.cognito_client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters={
                    "REFRESH_TOKEN": self.refresh_token,
                }
            )

            auth_result = response.get("AuthenticationResult", {})
            self.access_token = auth_result.get("AccessToken")
            self.id_token = auth_result.get("IdToken")

            return self.access_token is not None

        except ClientError as e:
            print(f"Token refresh error: {e}")
            return False

    def get_authorization_header(self) -> Dict[str, str]:
        """
        Get the Authorization header with current access token.

        Returns:
            Dictionary with Authorization header if token exists, empty dict otherwise
        """
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}

    def is_authenticated(self) -> bool:
        """Check if user is currently authenticated."""
        return self.access_token is not None


def get_cognito_auth(require_auth: bool = True) -> Optional[CognitoAuth]:
    """
    Get Cognito authentication instance with credentials from environment.

    Args:
        require_auth: If True, will try to authenticate using credentials

    Returns:
        CognitoAuth instance if configured, None otherwise
    """
    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    client_id = os.environ.get("COGNITO_CLIENT_ID")

    if not (user_pool_id and client_id):
        return None

    auth = CognitoAuth(user_pool_id, client_id)

    if require_auth:
        # Try to get credentials
        username = os.environ.get("COGNITO_USERNAME")
        password = os.environ.get("COGNITO_PASSWORD")

        if username and password:
            auth.authenticate(username, password)
        else:
            # Try to load cached token if available
            token_file = os.path.expanduser("~/.algo/cognito_token.json")
            if os.path.exists(token_file):
                try:
                    with open(token_file, "r") as f:
                        tokens = json.load(f)
                        auth.access_token = tokens.get("access_token")
                        auth.refresh_token = tokens.get("refresh_token")
                        auth.id_token = tokens.get("id_token")
                except Exception as e:
                    print(f"Failed to load cached token: {e}")

    return auth


def save_tokens(auth: CognitoAuth) -> None:
    """Save tokens to file for later use."""
    token_file = os.path.expanduser("~/.algo/cognito_token.json")
    os.makedirs(os.path.dirname(token_file), exist_ok=True)

    tokens = {
        "access_token": auth.access_token,
        "refresh_token": auth.refresh_token,
        "id_token": auth.id_token,
    }

    with open(token_file, "w") as f:
        json.dump(tokens, f)
