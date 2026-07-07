#!/usr/bin/env python3
"""Test dashboard data fetching with Cognito auth."""
import sys
import os

sys.path.insert(0, os.getcwd())

from dashboard.api_data_layer import set_cognito_auth
from dashboard.cognito_auth import CognitoAuth
from dashboard.fetchers import load_all

# Set up Cognito authentication first
cognito_user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
cognito_client_id = os.getenv('COGNITO_CLIENT_ID')
cognito_username = os.getenv('COGNITO_USERNAME')
cognito_password = os.getenv('COGNITO_PASSWORD')

print(f'Setting up Cognito auth for {cognito_username}...')
auth = CognitoAuth(cognito_user_pool_id, cognito_client_id)
if auth.authenticate(cognito_username, cognito_password):
    print('Cognito authentication successful')
    set_cognito_auth(auth)
else:
    print('Cognito authentication failed')
    sys.exit(1)

print('\nLoading dashboard data with auth...')
data = load_all()

print(f'Fetched keys: {list(data.keys())}')
print(f'Total keys: {len(data)}')

# Check for errors in the data
errors = {}
for key, value in data.items():
    if isinstance(value, dict) and '_error' in value:
        errors[key] = value['_error']

if errors:
    print(f'\nErrors found ({len(errors)}):')
    for key, error in list(errors.items())[:15]:
        print(f'  {key}: {error[:100]}')
else:
    print('\nNo errors found in data - all endpoints working!')

# Print sample data from critical endpoints
for key in ['port', 'perf', 'pos', 'mkt', 'cfg', 'sig', 'risk', 'health', 'run']:
    if key in data:
        val = data[key]
        if isinstance(val, dict):
            has_error = '_error' in val
            keys_list = [k for k in val.keys() if k != '_error'][:5]
            print(f'\n{key}: {type(val).__name__}, has_error={has_error}, keys={keys_list}')
            if has_error:
                print(f'     Error: {val["_error"][:100]}')
