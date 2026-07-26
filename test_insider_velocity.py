#!/usr/bin/env python3
"""Test insider velocity aggregator to see what's blocking data."""

import logging
from datetime import date

from utils.external.sec_form345_transaction_velocity import Form345TransactionVelocityAggregator

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

print("Testing Form345TransactionVelocityAggregator with AAPL")
print("=" * 60)

agg = Form345TransactionVelocityAggregator(lookback_quarters=4)

try:
    metrics = agg.get_velocity_metrics('AAPL', date.today())

    print("\nMetrics for AAPL:")
    print(f"  data_unavailable: {metrics.data_unavailable}")
    print(f"  reason: {metrics.reason}")
    print(f"  buy_transactions_30d: {metrics.buy_transactions_30d}")
    print(f"  sell_transactions_30d: {metrics.sell_transactions_30d}")
    print(f"  buy_transactions_90d: {metrics.buy_transactions_90d}")
    print(f"  sell_transactions_90d: {metrics.sell_transactions_90d}")
    print(f"  total_buy_shares_30d: {metrics.total_buy_shares_30d}")
    print(f"  total_sell_shares_30d: {metrics.total_sell_shares_30d}")

    # Check internal state
    print("\nAggregator state:")
    print(f"  Quarters loaded: {agg._quarters_loaded}")
    print(f"  Quarters attempted: {agg._quarters_attempted}")
    print(f"  Symbols with data: {len(agg._transactions)}")
    print(f"  AAPL in transactions: {'AAPL' in agg._transactions}")

    if 'AAPL' in agg._transactions:
        aapl_txns = agg._transactions['AAPL']
        print(f"  AAPL transactions: {len(aapl_txns)}")
        if aapl_txns:
            print(f"    Sample: {aapl_txns[0]}")

except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
