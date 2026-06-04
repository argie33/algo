#!/usr/bin/env python3
"""
Fix Cognito users - deletes old test users and creates correct ones
Run via: python scripts/fix-cognito-users.py
"""
import boto3
import sys

def fix_cognito_users():
    client = boto3.client('cognito-idp', region_name='us-east-1')

    pool_id = 'us-east-1_XJpLb9SKX'
    password = 'Bullseye@2026'

    print("=== Deleting old users ===")
    response = client.list_users(UserPoolId=pool_id)
    for user in response['Users']:
        username = user['Username']
        print(f"Deleting: {username}")
        try:
            client.admin_delete_user(UserPoolId=pool_id, Username=username)
            print(f"  ✓ Deleted")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print("\n=== Creating new users ===")

    # Create admin user with email as username
    users_to_create = [
        {
            'username': 'admin@stocks.local',
            'email': 'admin@stocks.local',
            'display_name': 'Admin'
        },
        {
            'username': 'edgebrookecapital@gmail.com',
            'email': 'edgebrookecapital@gmail.com',
            'display_name': 'Edgebrook Capital'
        }
    ]

    for user_config in users_to_create:
        username = user_config['username']
        email = user_config['email']

        print(f"Creating user: {username}")
        try:
            client.admin_create_user(
                UserPoolId=pool_id,
                Username=username,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'email_verified', 'Value': 'true'}
                ],
                MessageAction='SUPPRESS'
            )
            print(f"  ✓ Created")

            # Set permanent password
            client.admin_set_user_password(
                UserPoolId=pool_id,
                Username=username,
                Password=password,
                Permanent=True
            )
            print(f"  ✓ Password set: {password}")

        except Exception as e:
            print(f"  ✗ Error: {e}")

    print("\n=== Final users in pool ===")
    response = client.list_users(UserPoolId=pool_id)
    for user in response['Users']:
        email_attr = next((attr['Value'] for attr in user['Attributes'] if attr['Name'] == 'email'), 'N/A')
        print(f"  {user['Username']} (email: {email_attr}) - Status: {user['UserStatus']}")

    print("\n✅ Done! Try logging in with:")
    print(f"  Username: admin@stocks.local")
    print(f"  Password: {password}")
    print(f"  OR")
    print(f"  Username: edgebrookecapital@gmail.com")
    print(f"  Password: {password}")

if __name__ == '__main__':
    try:
        fix_cognito_users()
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
