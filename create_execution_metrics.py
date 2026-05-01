#!/usr/bin/env python3
"""Create loader_execution_metrics table for performance tracking"""

import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv('.env.local')

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=int(os.getenv('DB_PORT', '5432')),
    user=os.getenv('DB_USER', 'stocks'),
    password=os.getenv('DB_PASSWORD'),
    dbname=os.getenv('DB_NAME', 'stocks')
)

cur = conn.cursor()

# Drop table if exists (for fresh setup)
cur.execute('DROP TABLE IF EXISTS loader_execution_metrics')

# Create metrics table
cur.execute('''
CREATE TABLE IF NOT EXISTS loader_execution_metrics (
  id SERIAL PRIMARY KEY,
  loader_name VARCHAR(255) NOT NULL,
  start_time TIMESTAMP NOT NULL DEFAULT NOW(),
  end_time TIMESTAMP,
  duration_seconds NUMERIC,
  rows_inserted INTEGER,
  rows_skipped INTEGER,
  symbols_processed INTEGER,
  symbols_failed INTEGER,
  speedup_vs_baseline NUMERIC,
  worker_count INTEGER,
  status VARCHAR(50) NOT NULL DEFAULT 'pending',
  error_message TEXT,
  aws_region VARCHAR(50),
  ecs_task_id VARCHAR(255),
  container_instance VARCHAR(255),
  git_commit VARCHAR(40),
  created_at TIMESTAMP DEFAULT NOW()
)
''')

# Create indexes for fast queries
cur.execute('''
CREATE INDEX IF NOT EXISTS idx_loader_name ON loader_execution_metrics(loader_name)
''')

cur.execute('''
CREATE INDEX IF NOT EXISTS idx_status ON loader_execution_metrics(status)
''')

cur.execute('''
CREATE INDEX IF NOT EXISTS idx_start_time ON loader_execution_metrics(start_time DESC)
''')

# Create a view for recent performance
cur.execute('''
CREATE OR REPLACE VIEW loader_performance_summary AS
SELECT
  loader_name,
  COUNT(*) as total_runs,
  COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful_runs,
  COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_runs,
  ROUND(AVG(CASE WHEN status = 'completed' THEN duration_seconds END)::numeric, 1) as avg_duration_sec,
  MAX(CASE WHEN status = 'completed' THEN rows_inserted END) as max_rows_inserted,
  ROUND(AVG(CASE WHEN status = 'completed' THEN speedup_vs_baseline END)::numeric, 2) as avg_speedup,
  MAX(start_time) as last_run
FROM loader_execution_metrics
WHERE start_time > NOW() - INTERVAL '30 days'
GROUP BY loader_name
ORDER BY max_rows_inserted DESC NULLS LAST
''')

conn.commit()
conn.close()

print('[OK] Created loader_execution_metrics table')
print('[OK] Created performance summary view')
print('[OK] Created indexes for fast queries')
print('')
print('Next: Add logging to loaders using:')
print('')
print('  from datetime import datetime')
print('  ')
print('  def log_execution_metric(loader_name, start_time, end_time, rows_inserted,')
print('                          symbols_processed, worker_count=1):')
print('      conn = get_db_connection()')
print('      cur = conn.cursor()')
print('      ')
print('      duration = (end_time - start_time).total_seconds()')
print('      speedup = 3600 / duration  # baseline is 60 minutes for serial')
print('      ')
print('      cur.execute("""')
print('          INSERT INTO loader_execution_metrics')
print('          (loader_name, start_time, end_time, duration_seconds, rows_inserted,')
print('           symbols_processed, worker_count, speedup_vs_baseline, status)')
print('          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)')
print('      """, (loader_name, start_time, end_time, duration, rows_inserted,')
print('            symbols_processed, worker_count, speedup, "completed"))')
print('      ')
print('      conn.commit()')
print('      conn.close()')
