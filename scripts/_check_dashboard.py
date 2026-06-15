#!/usr/bin/env python3
"""Check VIX data and circuit breaker details."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools', 'dashboard'))
os.environ.setdefault('AWS_PROFILE', 'algo-developer')

import boto3
try:
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId='algo/dashboard-config')
    secret = json.loads(response['SecretString'])
    os.environ['DASHBOARD_API_URL'] = secret.get('api_url', '')
    os.environ['COGNITO_USER_POOL_ID'] = secret.get('cognito_user_pool_id', '')
    os.environ['COGNITO_CLIENT_ID'] = secret.get('cognito_user_pool_client_id', '')
except Exception as e:
    print(f'Secrets Manager: {e}'); sys.exit(1)

from utilities import set_api_url, set_cognito_auth, api_call
set_api_url(os.environ['DASHBOARD_API_URL'])
from cognito_auth import get_cognito_auth, save_tokens
auth = get_cognito_auth(require_auth=True)
if auth and auth.is_authenticated():
    set_cognito_auth(auth); save_tokens(auth)

# Full raw markets response
print('=== FULL MARKET HEALTH RAW ===')
mkt_raw = api_call('/api/algo/markets')
mkt_data = mkt_raw.get('data', {})
print(json.dumps(mkt_data.get('market_health', {}), indent=2, default=str))

# Full circuit breaker response
print()
print('=== FULL CIRCUIT BREAKERS RAW ===')
cb_raw = api_call('/api/algo/circuit-breakers')
print(json.dumps(cb_raw.get('data', {}), indent=2, default=str))
