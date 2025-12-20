#!/bin/bash
# This wrapper redirects table names from stock to ETF

export TABLE_OVERRIDE="buy_sell_daily_etf"
export PRICE_TABLE_OVERRIDE="etf_price_daily"
export SYMBOL_TABLE_OVERRIDE="etf_symbols"

# But the problem is the stock loader doesn't read these env vars...
# We need a different approach

echo "The wrapper approach won't work - stock loaders hardcode table names"
