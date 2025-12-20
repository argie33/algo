import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv('/home/stocks/algo/.env.local')

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_NAME = os.environ.get("DB_NAME", "stocks")

conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=== CHECKING MOST RECENT RECORDS ===\n")

for timeframe in ['daily', 'weekly', 'monthly']:
    table = f'buy_sell_{timeframe}_etf'
    
    # Get most recent date in table
    query = f"SELECT MAX(date) as latest_date FROM {table}"
    cur.execute(query)
    latest = cur.fetchone()['latest_date']
    
    # Check signals for that date
    query = f"""
    SELECT signal, COUNT(*) as count
    FROM {table}
    WHERE date = %s
    GROUP BY signal
    ORDER BY count DESC
    """
    cur.execute(query, (latest,))
    results = cur.fetchall()
    
    print(f"\n{timeframe.upper()} ({latest}):")
    total = sum(r['count'] for r in results)
    for r in results:
        sig = r['signal'] if r['signal'] else 'HOLD (NULL)'
        pct = (r['count']/total*100) if total > 0 else 0
        print(f"  {sig}: {r['count']} ({pct:.1f}%)")
    
    # Show sample records
    print(f"\n  Sample records:")
    query = f"""
    SELECT symbol, date, signal, close, buylevel, stoplevel, market_stage, stage_confidence
    FROM {table}
    WHERE date = %s
    ORDER BY symbol
    LIMIT 5
    """
    cur.execute(query, (latest,))
    for row in cur.fetchall():
        sig = row['signal'] if row['signal'] else 'HOLD'
        stage = row['market_stage'] if row['market_stage'] else 'None'
        conf = row['stage_confidence'] if row['stage_confidence'] else 'None'
        print(f"    {row['symbol']}: {sig:4s} | Close: ${row['close']:.2f} | Stage: {stage} | Conf: {conf}")

conn.close()
