import boto3
import psycopg2
import json
from datetime import datetime, timedelta

# Get database credentials from Secrets Manager
session = boto3.Session(profile_name='algo-developer')
sm_client = session.client('secretsmanager', region_name='us-east-1')

try:
    secret = sm_client.get_secret_value(SecretId='algo/database')
    db_secret = json.loads(secret['SecretString'])
except:
    secret = sm_client.get_secret_value(SecretId='algo-db-credentials-dev')
    db_secret = json.loads(secret['SecretString'])

# Connect to database
conn = psycopg2.connect(
    host=db_secret['host'],
    port=db_secret['port'],
    database=db_secret['dbname'],
    user=db_secret['username'],
    password=db_secret['password'],
    sslmode='require'
)

cursor = conn.cursor()

# Check data coverage
print("=" * 80)
print("DATA COVERAGE REPORT")
print("=" * 80)

# 1. Check stock_symbols
cursor.execute("SELECT COUNT(*) FROM stock_symbols")
symbol_count = cursor.fetchone()[0]
print(f"\n1. STOCK SYMBOLS")
print(f"   Total symbols: {symbol_count}")

# 2. Check price_daily coverage
cursor.execute("""
    SELECT symbol, MAX(date) as latest_date, COUNT(*) as record_count
    FROM price_daily
    GROUP BY symbol
    ORDER BY latest_date DESC, symbol
    LIMIT 20
""")
print(f"\n2. PRICE_DAILY (top 20 symbols by latest date)")
print(f"   {'Symbol':<10} {'Latest Date':<15} {'Records':<10}")
print(f"   {'-'*35}")
rows = cursor.fetchall()
for symbol, latest_date, count in rows:
    print(f"   {symbol:<10} {str(latest_date):<15} {count:<10}")

# 3. Check price_weekly coverage
cursor.execute("""
    SELECT symbol, MAX(date) as latest_date, COUNT(*) as record_count
    FROM price_weekly
    GROUP BY symbol
    ORDER BY latest_date DESC, symbol
    LIMIT 5
""")
print(f"\n3. PRICE_WEEKLY")
print(f"   {'Symbol':<10} {'Latest Date':<15} {'Records':<10}")
print(f"   {'-'*35}")
rows = cursor.fetchall()
if rows:
    for symbol, latest_date, count in rows:
        print(f"   {symbol:<10} {str(latest_date):<15} {count:<10}")
else:
    print("   NO DATA")

# 4. Check technical_data_daily coverage
cursor.execute("""
    SELECT symbol, MAX(date) as latest_date, COUNT(*) as record_count
    FROM technical_data_daily
    GROUP BY symbol
    ORDER BY latest_date DESC, symbol
    LIMIT 10
""")
print(f"\n4. TECHNICAL_DATA_DAILY (top 10 symbols)")
print(f"   {'Symbol':<10} {'Latest Date':<15} {'Records':<10}")
print(f"   {'-'*35}")
rows = cursor.fetchall()
if rows:
    for symbol, latest_date, count in rows:
        print(f"   {symbol:<10} {str(latest_date):<15} {count:<10}")
else:
    print("   NO DATA")

# 5. Check market_health_daily
cursor.execute("""
    SELECT MAX(date) as latest_date, COUNT(*) as record_count
    FROM market_health_daily
""")
result = cursor.fetchone()
print(f"\n5. MARKET_HEALTH_DAILY")
if result[0]:
    print(f"   Latest date: {result[0]}")
    print(f"   Records: {result[1]}")
else:
    print("   NO DATA")

# 6. Check data_loader_status
cursor.execute("""
    SELECT loader_name, MAX(executed_at) as latest_run, status, COUNT(*) as runs
    FROM data_loader_status
    WHERE executed_at > NOW() - INTERVAL '7 days'
    GROUP BY loader_name, status
    ORDER BY loader_name, latest_run DESC
""")
print(f"\n6. LOADER STATUS (Last 7 days)")
print(f"   {'Loader':<40} {'Latest Run':<20} {'Status':<10}")
print(f"   {'-'*70}")
rows = cursor.fetchall()
if rows:
    for loader, latest_run, status, count in rows:
        print(f"   {loader:<40} {str(latest_run):<20} {status:<10}")
else:
    print("   NO RECENT RUNS")

# 7. Check for missing critical tables
cursor.execute("""
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public'
    ORDER BY tablename
""")
all_tables = [row[0] for row in cursor.fetchall()]
critical_tables = [
    'stock_symbols', 'price_daily', 'technical_data_daily',
    'market_health_daily', 'trend_template_data', 'signal_quality_scores'
]

missing_tables = [t for t in critical_tables if t not in all_tables]

print(f"\n7. CRITICAL TABLES STATUS")
if missing_tables:
    print(f"   MISSING: {', '.join(missing_tables)}")
else:
    print(f"   All critical tables present")

conn.close()
print("\n" + "=" * 80)
