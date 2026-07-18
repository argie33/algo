#!/usr/bin/env python3
"""Check if API returns execution_health."""
import os
os.environ['LOCAL_MODE'] = 'true'
os.environ['ENVIRONMENT'] = 'development'

import sys
sys.path.insert(0, 'lambda/api/routes')
sys.path.insert(0, 'lambda/api/routes/algo_handlers')

import psycopg2
from psycopg2.extras import DictCursor

from algo_handlers.market import _get_data_status

conn = psycopg2.connect(
    host='localhost', user='stocks', password='stocks',
    database='stocks', cursor_factory=DictCursor
)
cur = conn.cursor()

result = _get_data_status(cur)

if 'data' in result and 'execution_health' in result['data']:
    eh = result['data']['execution_health']
    print("execution_health in response:")
    for k, v in eh.items():
        print(f"  {k}: {type(v).__name__}")
else:
    print("NO execution_health in response!")

cur.close()
conn.close()
