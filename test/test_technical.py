#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add parent directory to path
parent_dir = str(Path(__file__).resolve().parent.parent)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Mock resource for memory tracking
import types
import psutil

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

# Mock AWS dependencies
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

# Now run the loadtechnicalsdaily script
if __name__ == '__main__':
    os.environ['DB_SECRET_ARN'] = 'mock-secret'
    script_path = Path(parent_dir) / 'loadtechnicalsdaily.py'
    with open(script_path, encoding='utf-8') as f:
        exec(f.read())
