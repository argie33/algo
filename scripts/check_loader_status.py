#!/usr/bin/env python3
"""Check metrics loader status by verifying table population."""

import psycopg2
import sys
from datetime import datetime, timedelta
import os

def check_loader_status(hours_ago=24):
    """Query metrics tables to verify loader runs."""
    db_params = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'algo'),
        'user': os.getenv('DB_USER', 'algo_user'),
        'password': os.getenv('DB_PASSWORD'),
    }
    
    tables = {
        'quality_metrics': 'created_at',
        'growth_metrics': 'created_at',
        'positioning_metrics': 'created_at',
        'stability_metrics': 'created_at',
        'company_profile': 'updated_at',
    }
    
    try:
        conn = psycopg2.connect(**db_params)
        cur = conn.cursor()
        
        print(f"Checking metrics loader status (last {hours_ago} hours)...\n")
        
        for table, date_col in tables.items():
            try:
                cur.execute(f"""
                    SELECT 
                        count(*) as row_count,
                        MAX({date_col}) as latest_update
                    FROM {table}
                    WHERE {date_col} > NOW() - INTERVAL '{hours_ago} hours'
                """)
                row = cur.fetchone()
                count, latest = row if row else (0, None)
                
                if count > 0:
                    print(f"✓ {table}: {count} rows updated, latest: {latest}")
                else:
                    print(f"✗ {table}: No updates in {hours_ago} hours")
            except Exception as e:
                print(f"✗ {table}: Error - {e}")
        
        cur.close()
        conn.close()
        
    except psycopg2.OperationalError as e:
        print(f"ERROR: Cannot connect to database: {e}")
        print("Set DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME env vars")
        sys.exit(1)

if __name__ == '__main__':
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    check_loader_status(hours)
