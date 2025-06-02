#!/usr/bin/env python3
import yfinance as yf
import json
from pprint import pprint

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

    print("\n--- Growth Estimates ---")
    pprint(ticker.growth_estimates)  # Earnings trend data

    print("\n--- Quarterly Income Stmt---")
    pprint(ticker.quarterly_income_stmt)  # Earnings trend data

    print("\n--- Income Stmt---")
    pprint(ticker.income_stmt)  # Earnings trend data

    print("\n--- Quarterly balance_sheet---")
    pprint(ticker.quarterly_balance_sheet)  # Earnings trend data

    print("\n--- balance_sheet---")
    pprint(ticker.balance_sheet)  # Earnings trend data

    print("\n--- Quarterly cash flow---")
    pprint(ticker.quarterly_cash_flow)  # Earnings trend data

    print("\n--- cash flow---")
    pprint(ticker.cash_flow)  # Earnings trend data


    print("\n--- ttm_cash_flow---")
    pprint(ticker.ttm_cash_flow)  # Earnings trend data
   
    print("\n--- recommendations---")
    pprint(ticker.recommendations)  # Earnings trend data
   
    print("\n--- sec filings---")
    pprint(ticker.sec_filings)  # Earnings trend data
# Test with a few different stocks
symbols = ['AAPL']
for symbol in symbols:
    explore_earnings_data(symbol)
