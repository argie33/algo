#!/usr/bin/env python
import os
import sys
from sqlalchemy import create_engine, text

# Get credentials from env or pass as arguments
host = os.environ.get('DB_HOST') or 'algo-proxy.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com'
port = os.environ.get('DB_PORT', '5432')
user = os.environ.get('DB_USER', 'stocks')
password = os.environ.get('DB_PASSWORD', '')
dbname = os.environ.get('DB_NAME', 'stocks')

if not password:
    print("ERROR: DB_PASSWORD not set")
    sys.exit(1)

db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

try:
    engine = create_engine(db_url, echo=False)
    print(f"Connecting to {host}...")

    tables = ['prices', 'technical_data_daily', 'signals', 'buy_sell_daily', 'algo_runtime_config', 'stock_symbols', 'market_health_daily']

    with engine.connect() as conn:
        for table in tables:
            try:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"{table}: {count:,} rows")
            except Exception as e:
                print(f"{table}: ERROR - {e}")
except Exception as e:
    print(f"Connection error: {e}")
    sys.exit(1)
