#!/usr/bin/env python3
"""Test credential manager loading Alpaca credentials."""

import os

# Show what Python sees
print("Environment check:")
print(f"  APCA_API_KEY_ID: {'set' if os.getenv('APCA_API_KEY_ID') else 'NOT SET'}")
print(f"  APCA_API_SECRET_KEY: {'set' if os.getenv('APCA_API_SECRET_KEY') else 'NOT SET'}")
print("")

# Try to load credentials using the credential manager
try:
    from config.credential_manager import get_alpaca_credentials

    print("Attempting to load credentials via credential_manager...")
    creds = get_alpaca_credentials()
    print("[OK] SUCCESS: Alpaca credentials loaded via credential_manager!")
    print(f"  Key: {creds.get('key', 'N/A')[:15]}...")
    print(f"  Secret: {creds.get('secret', 'N/A')[:10]}...")
    exit(0)
except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")
    exit(1)
