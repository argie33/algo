#!/bin/bash
# Run after price loaders complete to finish signal generation
export $(cat .env.local | grep -v '^#' | xargs)

echo "FINISHING SIGNAL GENERATION PIPELINE"
echo "===================================="
echo ""

# Wait for price loaders to finish
echo "Checking if price loaders complete..."
while true; do
    pw=$(python3 -c "import psycopg2, os; conn = psycopg2.connect(host=os.environ['DB_HOST'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], database=os.environ['DB_NAME']); cur = conn.cursor(); cur.execute('SELECT COUNT(DISTINCT symbol) FROM price_weekly'); print(cur.fetchone()[0]); conn.close()")
    pm=$(python3 -c "import psycopg2, os; conn = psycopg2.connect(host=os.environ['DB_HOST'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], database=os.environ['DB_NAME']); cur = conn.cursor(); cur.execute('SELECT COUNT(DISTINCT symbol) FROM price_monthly'); print(cur.fetchone()[0]); conn.close()")
    pd=$(python3 -c "import psycopg2, os; conn = psycopg2.connect(host=os.environ['DB_HOST'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], database=os.environ['DB_NAME']); cur = conn.cursor(); cur.execute('SELECT COUNT(DISTINCT symbol) FROM price_daily'); print(cur.fetchone()[0]); conn.close()")

    if [ "$pw" -ge 4900 ] && [ "$pm" -ge 4900 ]; then
        echo "Prices complete! ($pw weekly, $pm monthly of $pd daily)"
        break
    else
        echo "Waiting... ($pw/$pd weekly, $pm/$pd monthly)"
        sleep 60
    fi
done

echo ""
echo "Running signal generators in parallel..."
timeout 3600 python3 loadbuysellweekly.py > /tmp/sig_weekly.log 2>&1 &
timeout 3600 python3 loadbuysellmonthly.py > /tmp/sig_monthly.log 2>&1 &
timeout 7200 python3 loadbuysell_etf_daily.py > /tmp/sig_etf_daily.log 2>&1 &
timeout 3600 python3 loadbuysell_etf_weekly.py > /tmp/sig_etf_weekly.log 2>&1 &
timeout 3600 python3 loadbuysell_etf_monthly.py > /tmp/sig_etf_monthly.log 2>&1 &

echo "Signal loaders started"
echo "Waiting for all to complete..."

wait

echo ""
echo "FINAL DATA CHECK:"
python3 << 'EOF'
import psycopg2, os
conn = psycopg2.connect(
    host=os.environ.get('DB_HOST'),
    user=os.environ.get('DB_USER'),
    password=os.environ.get('DB_PASSWORD'),
    database=os.environ.get('DB_NAME')
)
cur = conn.cursor()

tables = [
    ('buy_sell_daily', 'stock daily signals'),
    ('buy_sell_weekly', 'stock weekly signals'),
    ('buy_sell_monthly', 'stock monthly signals'),
    ('buy_sell_etf_daily', 'ETF daily signals'),
    ('buy_sell_etf_weekly', 'ETF weekly signals'),
    ('buy_sell_etf_monthly', 'ETF monthly signals'),
]

print("FINAL PIPELINE STATUS:")
for table, desc in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {desc}: {count:,}")
    except:
        print(f"  {desc}: TABLE MISSING")

conn.close()
EOF

echo ""
echo "Pipeline complete!"
