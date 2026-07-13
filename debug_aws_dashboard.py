#!/usr/bin/env python3
"""Debug AWS dashboard authentication flow."""

import json
import logging
import os
import sys

logging.basicConfig(level=logging.DEBUG, format='[%(name)s] %(message)s')
logger = logging.getLogger(__name__)

# Setup AWS credentials
os.environ.setdefault("DASHBOARD_API_URL", "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com")
os.environ.setdefault("COGNITO_USER_POOL_ID", "us-east-1_XJpLb9SKX")
os.environ.setdefault("COGNITO_CLIENT_ID", "6smb0vrcidd9kvhju2kn2a3qrl")
os.environ.setdefault("COGNITO_USERNAME", "argeropolos@gmail.com")
os.environ.setdefault("COGNITO_PASSWORD", "r96AsiSkXEjprsA1!")

# Import dashboard modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dashboard.cognito_auth import get_cognito_auth
from dashboard.api_data_layer import set_cognito_auth, api_call, get_api_url

print("\n" + "="*70)
print("AWS Dashboard Debug")
print("="*70)

# Step 1: Check API URL
api_url = get_api_url()
print(f"\n1. API URL: {api_url}")

# Step 2: Test Cognito authentication
print(f"\n2. Authenticating with Cognito...")
try:
    auth = get_cognito_auth(require_auth=True)
    if auth and hasattr(auth, 'access_token'):
        print(f"   ✓ Auth successful")
        print(f"   ✓ Access token: {auth.access_token[:50]}...")
        print(f"   ✓ Token expires at: {auth.token_expires_at}")

        # Get authorization header
        auth_header = auth.get_authorization_header()
        print(f"   ✓ Auth header: {auth_header['Authorization'][:50]}...")

        # Set it in API layer
        set_cognito_auth(auth)
        print(f"   ✓ Set in api_data_layer")
    else:
        print(f"   ✗ Auth failed: {auth}")
        sys.exit(1)
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 3: Make a test API call
print(f"\n3. Testing API call to /api/algo/status...")
try:
    result = api_call("/api/algo/status")
    if "_error" in result:
        print(f"   ✗ Error: {result['_error']}")
        if result.get("_auth_error"):
            print(f"      This is an AUTHENTICATION error")
        sys.exit(1)
    else:
        print(f"   ✓ API call successful!")
        print(f"   ✓ Response keys: {list(result.keys())}")
except Exception as e:
    print(f"   ✗ Exception: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*70)
print("All checks passed!")
print("="*70)
