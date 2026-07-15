#!/usr/bin/env python3
"""Test if Alpaca environment variables are accessible."""

import os

key_id = os.getenv("APCA_API_KEY_ID")
secret = os.getenv("APCA_API_SECRET_KEY")
base_url = os.getenv("APCA_API_BASE_URL")

print("Testing Alpaca environment variables:")
print(f"  APCA_API_KEY_ID: {key_id[:20] + '...' if key_id else '(NOT FOUND)'}")
print(f"  APCA_API_SECRET_KEY: {secret[:10] + '...' if secret else '(NOT FOUND)'}")
print(f"  APCA_API_BASE_URL: {base_url if base_url else '(NOT FOUND)'}")
print()

if key_id and secret:
    print("SUCCESS: Both Alpaca credentials found in Python!")
    exit(0)
else:
    print("FAILURE: Credentials not accessible to Python")
    print("\nAll env vars starting with APCA:")
    found = False
    for k, v in os.environ.items():
        if k.startswith('APCA'):
            print(f"  {k} = {v[:20] if len(v) > 20 else v}")
            found = True
    if not found:
        print("  (none found)")
    exit(1)
