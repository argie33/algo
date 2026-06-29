#!/bin/bash
# Validate AWS data loading infrastructure

echo ""
echo "========================================================================"
echo "DATA LOADING VALIDATION"
echo "========================================================================"
echo ""

# Check database connection
if [ -z "$DB_PASSWORD" ]; then
    echo "[CRITICAL] DB_PASSWORD environment variable required"
    exit 1
fi

# Run Python validation if available
if command -v python3 &> /dev/null; then
    python3 << 'PYTHON_EOF'
import os
import sys
from datetime import date, timedelta
try:
    import psycopg2
    import psycopg2.extras

    db_password = os.environ.get("DB_PASSWORD")
    if not db_password:
        raise ValueError("[CRITICAL] DB_PASSWORD required")

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ.get("DB_NAME", "algo_trading"),
        user=os.environ.get("DB_USER", "algo_user"),
        password=db_password
    )

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Query loader status
    cur.execute("""
        SELECT
            table_name,
            last_updated,
            status,
            completion_pct,
            symbol_count,
            symbols_loaded
        FROM data_loader_status
        ORDER BY table_name
    """)

    rows = cur.fetchall()

    critical_tables = {
        "stock_prices_daily",
        "market_health_daily",
        "stock_scores",
        "quality_metrics",
        "growth_metrics",
        "value_metrics",
        "stability_metrics",
        "positioning_metrics"
    }

    print("\n📊 LOADER STATUS:")
    print("-" * 80)

    ok = 0
    failed = 0
    incomplete = 0

    for row in rows:
        table = row["table_name"]
        status = row["status"]
        pct = (row["symbols_loaded"] / row["symbol_count"] * 100 if row["symbol_count"] else 0)
        is_crit = "🔴" if table in critical_tables else "🟡"

        if status == "error" or pct == 0:
            print(f"{is_crit} {table:30} ERROR   {pct:6.0f}%")
            failed += 1
        elif pct < 50:
            print(f"{is_crit} {table:30} INCOMPLETE {pct:5.0f}%")
            incomplete += 1
        else:
            print(f"✅ {table:30} OK      {pct:6.0f}%")
            ok += 1

    print("-" * 80)
    print(f"Summary: {ok} OK, {incomplete} incomplete, {failed} failed\n")

    if failed > 0 or incomplete > 0:
        sys.exit(1)

    cur.close()
    conn.close()

except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)
PYTHON_EOF
else
    echo "⚠️  Python not available - skipping detailed validation"
    echo "   Set DB_PASSWORD environment variable and re-run"
fi

echo "========================================================================"
echo ""
