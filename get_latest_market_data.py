#!/usr/bin/env python3
"""
Get Latest Market Data - Direct from yfinance
Loads current market data without requiring database connection
Useful for development/testing when database isn't available
"""

import yfinance as yf
import json
from datetime import datetime, timedelta
import sys

def get_market_indices():
    """Get latest market indices data"""
    print("📊 Fetching market indices...")

    indices = {
        '^GSPC': 'S&P 500',
        '^IXIC': 'NASDAQ Composite',
        '^DJI': 'Dow Jones Industrial Average',
        '^RUT': 'Russell 2000'
    }

    data = {}
    for symbol, name in indices.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1d')

            if not hist.empty:
                latest = hist.iloc[-1]
                prev_close = ticker.info.get('previousClose', latest['Open'])
                change = latest['Close'] - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0

                data[symbol] = {
                    'name': name,
                    'price': round(latest['Close'], 2),
                    'change': round(change, 2),
                    'changePercent': round(change_pct, 2),
                    'volume': int(latest['Volume']),
                    'date': str(hist.index[-1].date())
                }
                print(f"  ✅ {name}: ${data[symbol]['price']} ({change_pct:+.2f}%)")
        except Exception as e:
            print(f"  ❌ {name}: {str(e)[:50]}")

    return data

def get_sp500_pe():
    """Get S&P 500 P/E metrics"""
    print("\n📈 Fetching S&P 500 valuation metrics...")

    try:
        # Get ^GSPC price and info
        sp500 = yf.Ticker('^GSPC')
        info = sp500.info

        pe_data = {
            'symbol': '^GSPC',
            'trailing_pe': info.get('trailingPE'),
            'forward_pe': info.get('forwardPE'),
            'price_to_book': info.get('priceToBook'),
            'price_to_sales': info.get('priceToSalesTrailing12Months'),
            'dividend_yield': info.get('dividendYield'),
            'earnings_yield': 1 / info.get('trailingPE', 1) if info.get('trailingPE') else None
        }

        print(f"  ✅ S&P 500 P/E: {pe_data['trailing_pe']}")
        return pe_data
    except Exception as e:
        print(f"  ❌ Could not fetch P/E metrics: {e}")
        return {}

def get_sector_data():
    """Get sector ETF performance"""
    print("\n🏢 Fetching sector data...")

    sectors = {
        'XLK': 'Information Technology',
        'XLV': 'Healthcare',
        'XLF': 'Financials',
        'XLY': 'Consumer Discretionary',
        'XLP': 'Consumer Staples',
        'XLE': 'Energy',
        'XLRE': 'Real Estate',
        'XLI': 'Industrials',
        'XLU': 'Utilities',
        'XLRE': 'Real Estate',
        'XLM': 'Materials',
    }

    data = {}
    for ticker, name in sectors.items():
        try:
            etf = yf.Ticker(ticker)
            hist = etf.history(period='1d')

            if not hist.empty:
                latest = hist.iloc[-1]
                prev_close = etf.info.get('previousClose', latest['Open'])
                change_pct = ((latest['Close'] - prev_close) / prev_close * 100) if prev_close else 0

                data[ticker] = {
                    'name': name,
                    'symbol': ticker,
                    'price': round(latest['Close'], 2),
                    'change': round(latest['Close'] - prev_close, 2),
                    'changePercent': round(change_pct, 2),
                }
                print(f"  ✅ {name}: {change_pct:+.2f}%")
        except Exception as e:
            print(f"  ❌ {name}: {str(e)[:30]}")

    return data

def get_vix_data():
    """Get VIX volatility data"""
    print("\n😨 Fetching volatility (VIX)...")

    try:
        vix = yf.Ticker('^VIX')
        hist = vix.history(period='5d')

        if not hist.empty:
            latest = hist.iloc[-1]
            prev = hist.iloc[-2]['Close'] if len(hist) > 1 else latest['Open']
            change = latest['Close'] - prev

            data = {
                'price': round(latest['Close'], 2),
                'change': round(change, 2),
                'date': str(hist.index[-1].date()),
                '52w_high': round(hist['High'].max(), 2),
                '52w_low': round(hist['Low'].min(), 2)
            }
            print(f"  ✅ VIX: {data['price']} ({change:+.2f})")
            return data
    except Exception as e:
        print(f"  ❌ VIX: {e}")

    return {}

def main():
    print("="*60)
    print("LATEST MARKET DATA FETCHER")
    print("="*60)
    print(f"Timestamp: {datetime.now().isoformat()}\n")

    all_data = {
        'timestamp': datetime.now().isoformat(),
        'indices': get_market_indices(),
        'sp500_metrics': get_sp500_pe(),
        'sectors': get_sector_data(),
        'vix': get_vix_data()
    }

    # Display summary
    print("\n" + "="*60)
    print("MARKET SUMMARY")
    print("="*60)

    if all_data['indices']:
        print("\n📊 Market Indices:")
        for symbol, data in all_data['indices'].items():
            print(f"  {data['name']:30} {data['price']:>10,.2f}  {data['changePercent']:>+8.2f}%")

    if all_data['vix']:
        print(f"\n😨 Volatility: {all_data['vix']['price']}")

    # Export to JSON
    json_file = '/tmp/latest_market_data.json'
    with open(json_file, 'w') as f:
        json.dump(all_data, f, indent=2)
    print(f"\n✅ Data exported to {json_file}")

    # Also print for quick reference
    print("\n" + "="*60)
    print("JSON DATA (for API/Database import):")
    print("="*60)
    print(json.dumps(all_data, indent=2))

if __name__ == "__main__":
    main()
