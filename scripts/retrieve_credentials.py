import os
import json
import boto3

print("Attempting to retrieve Alpaca credentials from AWS Secrets Manager...")

region = os.getenv('AWS_REGION', 'us-east-1')
print(f"Region: {region}")

try:
    sm = boto3.client('secretsmanager', region_name=region)
    
    # Try specific secret names that Terraform would create
    secret_names = [
        'algo/alpaca',
        'algo-alpaca-dev',
        'algo-alpaca-api-keys',
        'alpaca-api-keys',
        'APCA_API_KEY_ID',
        'APCA_API_SECRET_KEY',
    ]
    
    found_creds = None
    for secret_name in secret_names:
        try:
            print(f"\nTrying to retrieve: {secret_name}")
            response = sm.get_secret_value(SecretId=secret_name)
            secret_string = response.get('SecretString')
            
            if secret_string:
                print(f"✓ Found secret: {secret_name}")
                try:
                    creds = json.loads(secret_string)
                    print(f"  Content: {list(creds.keys())}")
                    
                    # Check for Alpaca credentials
                    if 'APCA_API_KEY_ID' in creds and 'APCA_API_SECRET_KEY' in creds:
                        print(f"  ✓ Contains Alpaca credentials!")
                        found_creds = creds
                        break
                except:
                    print(f"  Not JSON, raw value length: {len(secret_string)}")
        except sm.exceptions.ResourceNotFoundException:
            print(f"✗ Not found")
        except Exception as e:
            print(f"✗ Error: {str(e)[:100]}")
    
    if found_creds:
        print("\n" + "="*60)
        print("SUCCESS! Found Alpaca credentials in AWS Secrets Manager")
        print("="*60)
        key_id = found_creds.get('APCA_API_KEY_ID')
        key_secret = found_creds.get('APCA_API_SECRET_KEY')
        
        print(f"APCA_API_KEY_ID: {key_id[:30]}..." if key_id else "APCA_API_KEY_ID: NOT FOUND")
        print(f"APCA_API_SECRET_KEY: [SET]" if key_secret else "APCA_API_SECRET_KEY: NOT FOUND")
        
        if key_id and key_secret:
            print("\nSetting environment variables...")
            os.environ['APCA_API_KEY_ID'] = key_id
            os.environ['APCA_API_SECRET_KEY'] = key_secret
            
            # Test the credentials
            print("Testing credentials with credential manager...")
            import sys
            sys.path.insert(0, '/'.join(__file__.split('/')[:-2]))
            from config.credential_manager import CredentialManager
            cm = CredentialManager()
            creds = cm.get_alpaca_credentials()
            print(f"✓ Credentials validated! API Key: {creds['key'][:20]}...")
    else:
        print("\n" + "="*60)
        print("CREDENTIALS NOT FOUND IN AWS SECRETS MANAGER")
        print("="*60)
        print("\nCredentials must be manually provided:")
        print("1. Go to https://alpaca.markets")
        print("2. Get your paper trading API keys")
        print("3. Store in AWS Secrets Manager or set environment variables")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
