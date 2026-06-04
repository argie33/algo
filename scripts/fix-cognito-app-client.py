#!/usr/bin/env python3
"""
Fix Cognito App Client - enable USER_PASSWORD_AUTH for username/password login
Run via: python scripts/fix-cognito-app-client.py
"""
import boto3

def fix_app_client():
    client = boto3.client('cognito-idp', region_name='us-east-1')

    pool_id = 'us-east-1_XJpLb9SKX'
    client_id = '6smb0vrcidd9kvhju2kn2a3qrl'

    print("=== Fixing Cognito App Client ===")
    print(f"Pool: {pool_id}")
    print(f"Client: {client_id}")
    print("")

    # Update app client to support all auth flows
    print("Updating auth flows to include USER_PASSWORD_AUTH...")
    client.update_user_pool_client(
        UserPoolId=pool_id,
        ClientId=client_id,
        ExplicitAuthFlows=[
            'ALLOW_USER_PASSWORD_AUTH',      # Enable direct username/password login
            'ALLOW_REFRESH_TOKEN_AUTH',      # Allow refresh token rotation
            'ALLOW_USER_SRP_AUTH',           # Keep SRP for security
            'ALLOW_CUSTOM_AUTH',             # Support custom auth if needed
        ]
    )

    print("✓ Updated app client")
    print("")

    # Verify
    print("=== Current App Client Config ===")
    response = client.describe_user_pool_client(
        UserPoolId=pool_id,
        ClientId=client_id
    )

    config = response['UserPoolClient']
    print(f"Client Name: {config['ClientName']}")
    print(f"Explicit Auth Flows:")
    for flow in config['ExplicitAuthFlows']:
        print(f"  - {flow}")

    print(f"Has Secret: {config.get('ClientSecret') is not None}")
    print(f"Prevent User Existence Errors: {config.get('PreventUserExistenceErrors', 'N/A')}")

    print("")
    print("✅ App client is now configured for username/password login!")
    print("")
    print("Try logging in with:")
    print("  Username: admin@stocks.local")
    print("  Password: Bullseye@2026")

if __name__ == '__main__':
    try:
        fix_app_client()
    except Exception as e:
        print(f"❌ Error: {e}", file=__import__('sys').stderr)
        import traceback
        traceback.print_exc()
        __import__('sys').exit(1)
