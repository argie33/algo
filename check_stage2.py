import psycopg2
import os

host = 'stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com'
user = 'stocks'
password = 'StocksProd2024!'
database = 'stocks'

try:
    # Try AWS RDS
    conn = psycopg2.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        connect_timeout=10
    )
    print("Connected to AWS RDS")
except psycopg2.OperationalError:
    # Try local
    try:
        conn = psycopg2.connect(
            host='localhost',
            user='stocks',
            database='stocks'
        )
        print("Connected to local database")
    except:
        print("ERROR: Could not connect to any database")
        exit(1)

with conn.cursor() as cur:
    # Check Stage 2 symbols
    cur.execute('''
        SELECT symbol, COUNT(*) as row_count, MAX(date) as latest_date
        FROM price_daily
        WHERE symbol IN ('BRK-B', 'LEN-B', 'WSO-B')
        GROUP BY symbol
        ORDER BY symbol
    ''')
    
    results = cur.fetchall()
    if results:
        print("\nStage 2 Symbol Data Status:")
        print("-" * 60)
        for symbol, count, latest in results:
            print(f"  {symbol}: {count} rows, latest: {latest}")
    else:
        print("\nNo Stage 2 data found. Checking if symbols exist in stock_symbols...")
        cur.execute('SELECT symbol FROM stock_symbols WHERE symbol IN (%s, %s, %s)', ('BRK-B', 'LEN-B', 'WSO-B'))
        symbols = [row[0] for row in cur.fetchall()]
        if symbols:
            print(f"  Symbols in stock_symbols: {symbols}")
        else:
            print("  Symbols NOT in stock_symbols table")

conn.close()
