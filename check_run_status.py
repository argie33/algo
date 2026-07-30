#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Setup path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Load env FIRST
from utils.dotenv_loader import load_env_local
load_env_local()

# Now safe to use DB
os.environ.setdefault("LOCAL_MODE", "true")

import psycopg2
from config.credential_manager import get_db_config

config = get_db_config()
conn = psycopg2.connect(
    dbname=config['database'],
    user=config['user'],
    password=config['password'],
    host=config['host'],
    port=config['port']
)
c = conn.cursor()

print("Today's orchestrator runs:")
print("=" * 100)

c.execute("""
    SELECT name, status, started_at AT TIME ZONE 'America/New_York' as started_et, 
           error_reason, phases
    FROM orchestrator_runs
    WHERE DATE(started_at AT TIME ZONE 'America/New_York') = CURRENT_DATE AT TIME ZONE 'America/New_York'
    ORDER BY started_at DESC
""")

runs = c.fetchall()
for name, status, started_et, error_reason, phases_json in runs:
    print(f"\n{name:50s} | {status:10s} | {str(started_et)[-8:]}")
    if status != 'success':
        print(f"  ERROR: {error_reason}")
    if phases_json:
        import json
        phases = json.loads(phases_json)
        # Count phase statuses
        phase_stats = {}
        for phase_list in phases.values():
            if isinstance(phase_list, list):
                for p in phase_list:
                    st = p.get('status', 'unknown')
                    phase_stats[st] = phase_stats.get(st, 0) + 1
        if phase_stats:
            print(f"  Phase counts: {phase_stats}")

conn.close()
print("\n" + "=" * 100)
