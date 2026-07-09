#!/usr/bin/env python3
"""Setup environment and run orchestrator test"""
import os
import sys
from utils.db import DatabaseContext

# Load environment from database
with DatabaseContext('read') as cur:
    cur.execute('''SELECT key, value FROM algo_config WHERE key IN
        ('alpaca_api_key_id', 'alpaca_api_secret_key', 'execution_mode', 'aws_account_id') ''')
    for key, value in cur.fetchall():
        if key == 'execution_mode':
            os.environ['ORCHESTRATOR_EXECUTION_MODE'] = value
        elif key == 'aws_account_id':
            os.environ['AWS_ACCOUNT_ID'] = value
        else:
            os.environ[key.upper()] = value

# Now run the orchestrator test
exec(open('run_end_to_end_test.py').read())
