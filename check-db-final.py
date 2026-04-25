import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2

load_dotenv(Path('.') / '.env.local')

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor()

# Check critical tables
tables = [
    'price_daily', 'price_weekly', 'price_monthly',
    'buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly',
    'technical_data_daily',
    'sector_ranking',
    'earnings_history',
    'quarterly_balance_sheet', 'quarterly_income_statement',
    'annual_balance_sheet', 'annual_income_statement',
    'stock_symbols'
]

print("CRITICAL TABLE STATUS:")
print("=" * 50)

for table in tables:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        symbol = "OK" if count > 0 else "EMPTY"
        print(f"{table.ljust(35)} : {str(count).rjust(10)} {symbol}")
    except:
        print(f"{table.ljust(35)} : NOT FOUND")

conn.close()
