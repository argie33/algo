#!/bin/bash
# Load environment
export $(cat .env.local | grep -v '^#' | xargs)

echo "🔄 SIGNAL GENERATION PIPELINE"
echo "════════════════════════════════════════════════════════════════"

# Function to run loader and verify
run_loader() {
    local loader=$1
    local table=$2
    echo ""
    echo "⏳ Starting: $loader"
    echo "---"

    timeout 3600 python3 "$loader" 2>&1 | tail -50

    if [ $? -eq 0 ]; then
        # Count records
        count=$(python3 << EOF
import psycopg2, os
conn = psycopg2.connect(host=os.environ.get('DB_HOST'), user=os.environ.get('DB_USER'), password=os.environ.get('DB_PASSWORD'), database=os.environ.get('DB_NAME'))
cur = conn.cursor()
cur.execute(f"SELECT COUNT(*) FROM $table")
print(cur.fetchone()[0])
conn.close()
EOF
)
        echo "✅ $loader: $count records in $table"
    else
        echo "❌ $loader FAILED"
    fi
}

# Run loaders in sequence
run_loader "loadbuyselldaily.py" "buy_sell_daily"
run_loader "loadbuysellweekly.py" "buy_sell_weekly"
run_loader "loadbuysellmonthly.py" "buy_sell_monthly"
run_loader "loadbuysell_etf_daily.py" "buy_sell_etf_daily"
run_loader "loadbuysell_etf_weekly.py" "buy_sell_etf_weekly"
run_loader "loadbuysell_etf_monthly.py" "buy_sell_etf_monthly"

echo ""
echo "✅ PIPELINE COMPLETE"
