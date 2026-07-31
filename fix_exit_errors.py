#!/usr/bin/env python3
"""
Clear exit errors for the 12 positions that failed with Alpaca auth issues on 2026-07-29.
These positions need to be re-evaluated with the current system (which should handle auth
errors gracefully by falling back to database prices in paper mode).
"""
from utils.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# List of symbols that had exit errors on 2026-07-29
problematic_symbols = ['AII', 'EPR', 'FBP', 'FRT', 'FVCB', 'GSL', 'HIG', 'MUFG', 'SEIC', 'SHBI', 'STRT', 'UL']

print('=== CLEARING EXIT ERRORS FOR 12 POSITIONS ===')
print('Symbols to clear:',', '.join(problematic_symbols))

# Clear the exit check errors for these symbols
cur.execute(
    """DELETE FROM algo_exit_check_errors
       WHERE symbol = ANY(%s)""",
    (problematic_symbols,)
)

deleted = cur.rowcount
print(f'Deleted {deleted} error records')

# Commit changes
conn.commit()

print('\n=== VERIFYING POSITIONS ARE READY FOR RE-EVALUATION ===')
cur.execute("""
    SELECT symbol, status, quantity, entry_date
    FROM algo_positions
    WHERE symbol = ANY(%s)
    ORDER BY symbol
""", (problematic_symbols,))

for symbol, status, quantity, entry_date in cur.fetchall():
    print(f'{symbol:6} | {status:8} | Qty: {quantity:7} | Entry: {entry_date}')

cur.close()
conn.close()

print('\n✓ Exit errors cleared. Positions ready for re-evaluation in next orchestrator run.')
