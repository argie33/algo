#!/usr/bin/env python3
"""Debug quarterly metrics computation."""

import os
os.environ.setdefault("LOCAL_MODE", "true")
os.environ.setdefault("ENVIRONMENT", "development")

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db.context import DatabaseContext

# Check AAPL quarterly data
with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT fiscal_quarter, fiscal_year, net_income, revenue, earnings_per_share
        FROM quarterly_income_statement
        WHERE symbol = 'AAPL'
        ORDER BY fiscal_year DESC, fiscal_quarter DESC
        LIMIT 8
    """)
    rows = cur.fetchall()

print(f"Found {len(rows)} quarterly records for AAPL:")
for row in rows:
    q, y, ni, rev, eps = row
    print(f"  Q{q} {y}: ni={ni}, rev={rev}, eps={eps}")

# Check how many quarters have complete data
if rows:
    print("\nLast 4 quarters analysis:")
    rows_rev = list(reversed(rows))
    last_4 = rows_rev[-4:]

    for i, row in enumerate(last_4):
        q, y, ni, rev, eps = row
        print(f"  [{i}] Q{q} {y}: ni={ni is not None}, rev={rev is not None}, eps={eps is not None}")

    # Test consecutive positive quarters logic
    consecutive = 0
    for row in last_4:
        _, _, ni, _, _ = row
        if ni is not None and ni > 0:
            consecutive += 1
        else:
            break
    print(f"\nConsecutive positive quarters at end: {consecutive}")

    # Test EPS growth rates
    eps_rates = []
    for i in range(1, len(last_4)):
        curr_eps = last_4[i][4]
        prev_eps = last_4[i-1][4]
        if curr_eps is not None and prev_eps is not None and prev_eps != 0:
            growth = ((curr_eps - prev_eps) / abs(prev_eps)) * 100
            eps_rates.append(growth)
            print(f"  Q{i-1}->Q{i}: {prev_eps} -> {curr_eps} = {growth:.2f}%")

    if eps_rates:
        avg = sum(eps_rates) / len(eps_rates)
        print(f"\nEPS growth rate average: {avg:.2f}%")
    else:
        print("\nNo EPS growth rates computed")
