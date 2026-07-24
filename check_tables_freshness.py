#!/usr/bin/env python3
import sys
from datetime import datetime, timezone
from utils.db.context import DatabaseContext

tables = ['company_info_sec', 'company_profile', 'algo_performance_metrics', 'algo_untracked_positions', 'equity_curve_daily']

for table in tables:
    try:
        with DatabaseContext('read') as cur:
            cur.execute(f'SELECT COUNT(*) FROM {table}')
            count = cur.fetchone()[0]
            # Try to get updated_at, created_at, or latest timestamp
            for col in ['updated_at', 'created_at', 'date', 'started_at']:
                try:
                    cur.execute(f'SELECT MAX({col}) FROM {table}')
                    ts = cur.fetchone()[0]
                    if ts:
                        now = datetime.now(timezone.utc)
                        if hasattr(ts, 'tzinfo') and ts.tzinfo:
                            age_hours = (now - ts).total_seconds() / 3600
                        else:
                            age_hours = (now - ts.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                        print(f'{table}: {count} rows, {age_hours:.1f}h old ({col})')
                        break
                except:
                    continue
            else:
                print(f'{table}: {count} rows, no timestamp column found')
    except Exception as e:
        print(f'{table}: ERROR - {str(e)[:60]}')
