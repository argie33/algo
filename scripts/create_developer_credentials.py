#!/usr/bin/env python3
"""
Create or rotate developer IAM access key and store in Secrets Manager.
Designed to run via GitHub Actions with OIDC authentication.

This script:
1. Lists existing access keys for algo-developer user
2. Creates a new access key
3. Updates Secrets Manager with the new credentials
4. Optionally deletes old keys
"""

import boto3
import json
import sys
from datetime import datetime

def main():
    region = 'us-east-1'
    username = 'algo-developer'
    secret_name = 'algo/developer-credentials'

    iam = boto3.client('iam', region_name=region)
    secrets = boto3.client('secretsmanager', region_name=region)

    try:
        # Ensure user exists
        print(f"=== Ensuring IAM User Exists ===")
        try:
            user_info = iam.get_user(UserName=username)
            print(f"✓ User exists: {user_info['User']['Arn']}")
        except iam.exceptions.NoSuchEntityException:
            print(f"User '{username}' not found. Creating...")
            user = iam.create_user(UserName=username)
            print(f"✓ Created user: {user['User']['Arn']}")
            # Attach read-only policy
            iam.attach_user_policy(
                UserName=username,
                PolicyArn='arn:aws:iam::aws:policy/ReadOnlyAccess'
            )
            print(f"✓ Attached ReadOnlyAccess policy")

        # List current keys
        print(f"\n=== Current Access Keys for {username} ===")
        keys_response = iam.list_access_keys(UserName=username)
        current_keys = keys_response.get('AccessKeyMetadata', [])

        for key in current_keys:
            print(f"  Key: {key['AccessKeyId'][:4]}...{key['AccessKeyId'][-4:]}")
            print(f"    Status: {key['Status']}")
            print(f"    Created: {key['CreateDate']}")

        # Delete all existing keys first (hit limit if >1 key exists)
        if len(current_keys) >= 2:
            print(f"\n=== Deleting Old Access Keys (hit quota limit) ===")
            for old_key in current_keys:
                old_key_id = old_key['AccessKeyId']
                print(f"Deleting: {old_key_id[:4]}...{old_key_id[-4:]}")
                try:
                    iam.delete_access_key(UserName=username, AccessKeyId=old_key_id)
                    print(f"  ✓ Deleted")
                except Exception as e:
                    print(f"  ✗ Failed to delete: {e}")
                    # Continue trying to delete other keys

        # Create new access key
        print(f"\n=== Creating New Access Key ===")
        new_key = iam.create_access_key(UserName=username)
        access_key_id = new_key['AccessKey']['AccessKeyId']
        secret_access_key = new_key['AccessKey']['SecretAccessKey']

        print(f"✓ New key created: {access_key_id[:4]}...{access_key_id[-4:]}")

        # Update Secrets Manager
        print(f"\n=== Updating Secrets Manager ===")
        secret_value = json.dumps({
            'access_key_id': access_key_id,
            'secret_access_key': secret_access_key,
            'user_name': username
        })

        try:
            secrets.put_secret_value(
                SecretId=secret_name,
                SecretString=secret_value
            )
            print(f"✓ Updated secret: {secret_name}")
        except Exception as e:
            if 'ResourceNotFoundException' in str(type(e)):
                print(f"✗ Secret not found: {secret_name}")
                print("Attempting to create it...")
                secrets.create_secret(
                    Name=secret_name,
                    SecretString=secret_value,
                    Description='Developer IAM user access keys'
                )
                print(f"✓ Created secret: {secret_name}")
            else:
                raise

        # Test new credentials
        print(f"\n=== Testing New Credentials ===")
        sts = boto3.client(
            'sts',
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key
        )

        try:
            identity = sts.get_caller_identity()
            arn = identity.get('Arn')
            print(f"✓ Credentials verified: {arn}")
        except Exception as e:
            print(f"✗ Credential verification failed: {e}")
            return 1

        # Clean up old keys (keep only the newest)
        print(f"\n=== Cleaning Up Old Keys ===")
        keys_response = iam.list_access_keys(UserName=username)
        all_keys = keys_response.get('AccessKeyMetadata', [])

        if len(all_keys) > 1:
            # Sort by creation date, keep newest
            all_keys.sort(key=lambda k: k['CreateDate'], reverse=True)
            old_keys = all_keys[1:]  # All except the newest

            for old_key in old_keys:
                old_key_id = old_key['AccessKeyId']
                print(f"Deleting old key: {old_key_id[:4]}...{old_key_id[-4:]}")
                try:
                    iam.delete_access_key(UserName=username, AccessKeyId=old_key_id)
                    print(f"  ✓ Deleted")
                except Exception as e:
                    print(f"  ✗ Failed to delete: {e}")
        else:
            print("No old keys to delete")

        print("\n=== Success ===")
        print(f"New credentials are ready. Run:")
        print(f"  scripts/refresh-aws-credentials.ps1")

        return 0

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
