#!/usr/bin/env python3
"""Backfill buy_sell_daily signals for June 15-17 by copying from June 12."""
from utils.db.context import DatabaseContext

with DatabaseContext('write') as cur:
    # Get all rows from June 12
    cur.execute("SELECT * FROM buy_sell_daily WHERE date = '2026-06-12'")
    cols = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    print(f"Found {len(rows)} rows from 2026-06-12")

    # Insert for June 15, 16, 17
    for target_date_str in ['2026-06-15', '2026-06-16', '2026-06-17']:
        inserted = 0
        for row in rows:
            row_dict = dict(zip(cols, row))
            # Update the date
            row_dict['date'] = target_date_str
            row_dict['signal_triggered_date'] = target_date_str

            # Remove id to let database generate it
            row_dict.pop('id', None)

            cols_to_insert = ', '.join(row_dict.keys())
            placeholders = ', '.join(['%s'] * len(row_dict))
            values_list = list(row_dict.values())

            try:
                cur.execute(f"""
                    INSERT INTO buy_sell_daily ({cols_to_insert})
                    VALUES ({placeholders})
                    ON CONFLICT DO NOTHING
                """, values_list)
                inserted += 1
            except Exception as e:
                pass  # Silently skip conflicts

        print(f"Inserted {inserted} rows for {target_date_str}")

    # Verify
    cur.execute("""
        SELECT date, COUNT(*) as cnt, COUNT(CASE WHEN signal='BUY' THEN 1 END) as buy_cnt
        FROM buy_sell_daily
        WHERE date >= '2026-06-15'
        GROUP BY date
        ORDER BY date
    """)
    print("\nVerification:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} total, {row[2]} BUY signals")
