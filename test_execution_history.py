#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.database_context import DatabaseContext

# Check data_loader_status to see which loaders have run
with DatabaseContext('read') as cur:
    # Check table exists
    cur.execute("SELECT to_regclass('data_loader_status')")
    exists = cur.fetchone()[0] is not None
    print(f'data_loader_status table exists: {exists}')

    if exists:
        cur.execute('SELECT COUNT(*) FROM data_loader_status')
        count = cur.fetchone()[0]
        print(f'Total loader status records: {count}')

        # Get loaders that have run recently
        cur.execute('''
            SELECT table_name, status, symbols_loaded, last_updated
            FROM data_loader_status
            ORDER BY last_updated DESC
            LIMIT 5
        ''')
        rows = cur.fetchall()
        if rows:
            print('\nLoaders that have run (most recent):')
            for row in rows:
                print(f'  {row[0]}: {row[1]} ({row[2]} symbols) at {row[3]}')
        else:
            print('No loader status records found')

    # Check execution history
    print('\n--- Execution History ---')
    cur.execute('SELECT COUNT(*) FROM loader_execution_history')
    count = cur.fetchone()[0]
    print(f'Total loader_execution_history records: {count}')

    if count == 0:
        print('[WARNING] loader_execution_history is EMPTY - issue confirmed!')
    else:
        cur.execute('SELECT loader_name, status, rows_processed FROM loader_execution_history ORDER BY created_at DESC LIMIT 3')
        rows = cur.fetchall()
        print('Most recent 3 records:')
        for row in rows:
            print(f'  {row[0]}: {row[1]} ({row[2]} rows)')
