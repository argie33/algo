#!/usr/bin/env python3
import json
import boto3
import psycopg2

# Get DB credentials
SECRET_ARN = "arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-fl3BxQ"
sm_client = boto3.client("secretsmanager")
secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
creds = json.loads(secret_resp["SecretString"])

conn = psycopg2.connect(
    host=creds["host"],
    port=int(creds.get("port", 5432)),
    user=creds["username"],
    password=creds["password"],
    dbname=creds["dbname"],
)
cur = conn.cursor()

# Check tables
tables = ['price_daily', 'price_weekly', 'price_monthly',
          'technical_data_daily', 'technical_data_weekly', 'technical_data_monthly']

for table in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table} LIMIT 1")
        count = cur.fetchone()[0]
        print(f"✓ {table}: {count:,} rows")
    except Exception as e:
        print(f"✗ {table}: {e}")

# Check a sample symbol for weekly and monthly data
test_symbol = 'AAPL'
for tf in ['weekly', 'monthly']:
    try:
        cur.execute(f"SELECT COUNT(*) FROM price_{tf} WHERE symbol = %s", (test_symbol,))
        count = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM technical_data_{tf} WHERE symbol = %s", (test_symbol,))
        tech_count = cur.fetchone()[0]
        print(f"✓ {test_symbol} {tf}: price={count}, technical={tech_count}")
    except Exception as e:
        print(f"✗ {test_symbol} {tf}: {e}")

cur.close()
conn.close()