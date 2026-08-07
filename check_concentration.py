import os
os.environ['DB_NAME'] = 'stocks'
from utils.db.connection import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()

# Check open positions value
cur.execute('''
    SELECT SUM(entry_price * quantity) as total_value
    FROM algo_trades
    WHERE entry_date = %s AND status = %s
''', (date(2026, 8, 6), 'open'))

open_value = cur.fetchone()[0]
print(f'Total open position value: ${open_value:,.2f}')

# Check portfolio value
cur.execute('''
    SELECT total_portfolio_value
    FROM equity_curve_daily
    WHERE date = %s
    ORDER BY date DESC LIMIT 1
''', (date(2026, 8, 6),))

port_value = cur.fetchone()
if port_value:
    pv = port_value[0]
    conc = (open_value / pv * 100) if pv > 0 else 0
    print(f'Portfolio value: ${pv:,.2f}')
    print(f'Total concentration: {conc:.2f}%')

    # Individual positions
    cur.execute('''
        SELECT symbol, SUM(entry_price * quantity) as value,
               100.0 * SUM(entry_price * quantity) / %s as pct
        FROM algo_trades
        WHERE entry_date = %s AND status = %s
        GROUP BY symbol
        ORDER BY pct DESC
    ''', (pv, date(2026, 8, 6), 'open'))

    print('\n=== OPEN POSITIONS ===')
    for row in cur.fetchall():
        print(f'{row[0]}: ${row[1]:,.2f} ({row[2]:.3f}%)')

conn.close()
