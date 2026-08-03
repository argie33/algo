from utils.db import DatabaseContext

with DatabaseContext() as cur:
    print("=== CHECK: Do INSW/EOG positions have corresponding trades? ===")

    for symbol in ['INSW', 'EOG']:
        cur.execute("""
        SELECT t.trade_id, t.cognito_sub, t.created_at
        FROM algo_trades t
        WHERE t.symbol = %s AND t.status IN ('open', 'filled')
        ORDER BY t.created_at DESC
        LIMIT 3
        """, (symbol,))

        trades = cur.fetchall()
        print(f"\n{symbol}:")
        if trades:
            for trade_id, cognito_sub, created_at in trades:
                cog_str = cognito_sub if cognito_sub else "NULL"
                print(f"  {trade_id}: cognito_sub={cog_str}, created={created_at}")
        else:
            print("  No trades found")

    # Check when the position_sync run happened
    print("\n=== CHECK: Last position_sync runs ===")
    cur.execute("""
    SELECT entity_type, operation_type, MAX(created_at) as last_run, COUNT(*) as count
    FROM algo_audit_log
    WHERE entity_type = 'position' OR operation_type LIKE '%sync%'
    GROUP BY entity_type, operation_type
    ORDER BY last_run DESC
    LIMIT 10
    """)

    runs = cur.fetchall()
    for entity_type, op_type, last_run, count in runs:
        print(f"{op_type}: {count} operations, last at {last_run}")
