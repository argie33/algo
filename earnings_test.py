#!/usr/bin/env python3
import json
from pprint import pprint

import yfinance as yf


def explore_earnings_data(symbol):
    print(f"\n=== Exploring earnings data for {symbol} ===")
    ticker = yf.Ticker(symbol)

    print("\n--- Earnings Calendar ---")
    pprint(ticker.calendar)  # Historical earnings data

    print("\n--- Earnings Estimate ---")
    pprint(ticker.earnings_estimate)  # Historical earnings data

    print("\n--- Revenue Estimate ---")
    pprint(ticker.revenue_estimate)  # Historical earnings data

    print("\n--- Earnings History ---")
    pprint(ticker.earnings_history)

    print("\n--- EPS Revisions ---")
    pprint(ticker.eps_revisions)  # Upcoming and recent earnings dates

    print("\n--- Earnings Trend ---")
    pprint(ticker.eps_trend)  # Earnings trend data


# Test with a few different stocks
symbols = ["AAPL", "MSFT", "GOOGL"]
for symbol in symbols:
    explore_earnings_data(symbol)
