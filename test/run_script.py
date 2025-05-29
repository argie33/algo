#!/usr/bin/env python3
import os
import sys
import psutil
from pathlib import Path

# Add parent directory to path so we can import the original scripts
parent_dir = str(Path(__file__).resolve().parent.parent)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Patch resource module for Windows
import types
def mock_getrusage(who):
    class Usage:
        def __init__(self):
            process = psutil.Process()
            self.ru_maxrss = int(process.memory_info().rss / 1024)  # Convert to KB
    return Usage()

mock_resource = types.ModuleType('resource')
setattr(mock_resource, 'getrusage', mock_getrusage)
setattr(mock_resource, 'RUSAGE_SELF', 0)
sys.modules['resource'] = mock_resource

# Override AWS dependencies
import boto3
def mock_get_secret(*args, **kwargs):
    return {
        'SecretString': '''{
            "host": "localhost",
            "port": 5432,
            "username": "postgres",
            "password": "postgres",
            "dbname": "stocks"
        }'''
    }
boto3.client = lambda *args, **kwargs: type('MockClient', (), {'get_secret_value': mock_get_secret})()

# Now we can safely import and run the original script
if __name__ == '__main__':
    script_name = sys.argv[1] if len(sys.argv) > 1 else 'loadstocksymbols.py'
    os.environ['DB_SECRET_ARN'] = 'mock-secret'  # Mock value
    script_path = Path(parent_dir) / script_name
    exec(open(script_path).read())
