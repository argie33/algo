#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from utils.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM algo_trades WHERE created_at > NOW() - INTERVAL \'1 hour\'')
count = cursor.fetchone()[0]
print(f'Trades created in last hour: {count}')

cursor.execute('SELECT MAX(created_at) FROM algo_trades')
newest = cursor.fetchone()[0]
print(f'Newest trade: {newest}')

conn.close()
