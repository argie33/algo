#!/usr/bin/env python3
"""
Comprehensive Fresh Market Data Fetcher
Loads all market data directly from yfinance and external APIs
No database connection needed - serves all pages with fresh data
"""

import yfinance as yf
import json
import pandas as pd
from datetime import datetime, timedelta
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def get_market_indices():
    """Get latest market indices data"""
    logging.info("📊 Fetching market indices...")

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
            hist = ticker.history(period='5d')

            if not hist.empty:
                latest = hist.iloc[-1]
                prev_close = ticker.info.get('previousClose', latest['Open'])
                change = latest['Close'] - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0

                data[symbol] = {
                    'name': name,
                    'symbol': symbol,
                    'price': round(latest['Close'], 2),
                    'change': round(change, 2),
                    'changePercent': round(change_pct, 2),
                    'volume': int(latest['Volume']),
                    'date': str(hist.index[-1].date()),
                    '52w_high': round(hist['High'].max(), 2),
                    '52w_low': round(hist['Low'].min(), 2)
                }
        except Exception as e:
            logging.warning(f"  ⚠️ {name}: {str(e)[:50]}")

    return data

def get_sector_data():
    """Get sector ETF performance"""
    logging.info("🏢 Fetching sector data...")

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
    }

    data = {}
    for ticker, name in sectors.items():
        try:
            etf = yf.Ticker(ticker)
            hist = etf.history(period='5d')

            if not hist.empty:
                latest = hist.iloc[-1]
                prev_close = etf.info.get('previousClose', latest['Open'])
                change = latest['Close'] - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0

                data[ticker] = {
                    'name': name,
                    'symbol': ticker,
                    'price': round(latest['Close'], 2),
                    'change': round(change, 2),
                    'changePercent': round(change_pct, 2),
                    'volume': int(latest['Volume']),
                    'date': str(hist.index[-1].date()),
                    'performance': round(change_pct, 2)
                }
        except Exception as e:
            logging.warning(f"  ⚠️ {name}: {str(e)[:30]}")

    return data

def get_industry_data():
    """Get industry sector data"""
    logging.info("🏭 Fetching industry data...")

    # Major industry ETFs
    industries = {
        'XBI': 'Biotechnology',
        'XRT': 'Retail',
        'XHB': 'Home Builders',
        'XPH': 'Pharmaceuticals',
        'XES': 'Oil & Gas Exploration',
        'XME': 'Mining',
        'XLU': 'Utilities',
        'SOXX': 'Semiconductors',
    }

    data = {}
    for ticker, name in industries.items():
        try:
            etf = yf.Ticker(ticker)
            hist = etf.history(period='5d')

            if not hist.empty:
                latest = hist.iloc[-1]
                prev_close = etf.info.get('previousClose', latest['Open'])
                change_pct = ((latest['Close'] - prev_close) / prev_close * 100) if prev_close else 0

                data[ticker] = {
                    'name': name,
                    'symbol': ticker,
                    'price': round(latest['Close'], 2),
                    'changePercent': round(change_pct, 2),
                    'rank': 0  # Will be calculated
                }
        except Exception as e:
            logging.warning(f"  ⚠️ {name}: {str(e)[:30]}")

    # Rank by performance
    sorted_industries = sorted(data.items(), key=lambda x: x[1]['changePercent'], reverse=True)
    for idx, (ticker, ind) in enumerate(sorted_industries, 1):
        data[ticker]['rank'] = idx

    return data

def get_vix_data():
    """Get VIX volatility data"""
    logging.info("😨 Fetching volatility (VIX)...")

    try:
        vix = yf.Ticker('^VIX')
        hist = vix.history(period='30d')

        if not hist.empty:
            latest = hist.iloc[-1]
            prev = hist.iloc[-2]['Close'] if len(hist) > 1 else latest['Open']
            change = latest['Close'] - prev

            data = {
                'symbol': '^VIX',
                'price': round(latest['Close'], 2),
                'change': round(change, 2),
                'date': str(hist.index[-1].date()),
                '52w_high': round(hist['High'].max(), 2),
                '52w_low': round(hist['Low'].min(), 2),
                'interpretation': get_vix_interpretation(latest['Close'])
            }
            return data
    except Exception as e:
        logging.warning(f"  ⚠️ VIX: {e}")

    return {}

def get_vix_interpretation(vix_value):
    """Interpret VIX level"""
    if vix_value < 12:
        return "Very Low Volatility - Complacency"
    elif vix_value < 16:
        return "Low Volatility - Calm Market"
    elif vix_value < 20:
        return "Normal Volatility - Balanced"
    elif vix_value < 25:
        return "Elevated Volatility - Caution"
    else:
        return "High Volatility - Fear"

def get_major_stocks():
    """Get top stocks for earnings tracking"""
    logging.info("📈 Fetching major stocks...")

    major_stocks = [
        ('AAPL', 'Apple'),
        ('MSFT', 'Microsoft'),
        ('GOOGL', 'Alphabet'),
        ('AMZN', 'Amazon'),
        ('NVDA', 'NVIDIA'),
        ('TSLA', 'Tesla'),
        ('META', 'Meta'),
        ('GOOG', 'Google'),
        ('BRK.B', 'Berkshire Hathaway'),
        ('JPM', 'JPMorgan Chase'),
    ]

    data = {}
    for ticker, name in major_stocks:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period='5d')

            if not hist.empty:
                latest = hist.iloc[-1]
                prev_close = stock.info.get('previousClose', latest['Open'])
                change_pct = ((latest['Close'] - prev_close) / prev_close * 100) if prev_close else 0

                info = stock.info
                data[ticker] = {
                    'symbol': ticker,
                    'name': name,
                    'price': round(latest['Close'], 2),
                    'changePercent': round(change_pct, 2),
                    'pe': info.get('trailingPE'),
                    'eps': info.get('epsTrailingTwelveMonths'),
                    'marketCap': info.get('marketCap'),
                    'date': str(hist.index[-1].date())
                }
        except Exception as e:
            logging.warning(f"  ⚠️ {name}: {str(e)[:30]}")

    return data

def get_economic_indicators():
    """Get economic indicator proxies (using related ETFs)"""
    logging.info("💰 Fetching economic indicators...")

    # ETFs that track economic sectors/indicators
    economic_indicators = {
        'IYR': 'Real Estate (Economic Health)',
        'XLI': 'Industrials (Economic Growth)',
        'XLY': 'Consumer Discretionary (Consumer Strength)',
        'USO': 'Oil Prices',
        'GLD': 'Gold (Inflation/Fear)',
        'TLT': 'Long-term Treasury (Interest Rates)',
        'UUP': 'Dollar Index (Currency Strength)',
    }

    data = {}
    for ticker, name in economic_indicators.items():
        try:
            etf = yf.Ticker(ticker)
            hist = etf.history(period='30d')

            if not hist.empty:
                latest = hist.iloc[-1]
                prev_close = etf.info.get('previousClose', latest['Open'])
                change_pct = ((latest['Close'] - prev_close) / prev_close * 100) if prev_close else 0

                data[ticker] = {
                    'name': name,
                    'symbol': ticker,
                    'price': round(latest['Close'], 2),
                    'changePercent': round(change_pct, 2),
                    'change_30d': round((latest['Close'] - hist.iloc[0]['Close']) / hist.iloc[0]['Close'] * 100, 2),
                    'date': str(hist.index[-1].date())
                }
        except Exception as e:
            logging.warning(f"  ⚠️ {name}: {str(e)[:30]}")

    return data

def get_market_breadth():
    """Get market breadth indicators using major indices"""
    logging.info("📊 Calculating market breadth...")

    # Use S&P 500 as proxy for breadth
    try:
        sp500 = yf.Ticker('^GSPC')
        hist = sp500.history(period='5d')

        if len(hist) > 1:
            latest = hist.iloc[-1]
            prev = hist.iloc[-2]
            ma_20 = hist['Close'].tail(20).mean() if len(hist) >= 20 else latest['Close']
            ma_50 = hist['Close'].tail(50).mean() if len(hist) >= 50 else latest['Close']

            data = {
                'price': round(latest['Close'], 2),
                'above_ma20': latest['Close'] > ma_20,
                'above_ma50': latest['Close'] > ma_50,
                'ma_20': round(ma_20, 2),
                'ma_50': round(ma_50, 2),
                'breadth_strength': 'Strong' if latest['Close'] > ma_20 else 'Weak',
                'trend': 'Uptrend' if ma_20 > ma_50 else 'Downtrend'
            }
            return data
    except Exception as e:
        logging.warning(f"  ⚠️ Breadth: {e}")

    return {}

def main():
    logging.info("="*60)
    logging.info("COMPREHENSIVE MARKET DATA FETCHER")
    logging.info("="*60)

    all_data = {
        'timestamp': datetime.now().isoformat(),
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'indices': get_market_indices(),
        'sectors': get_sector_data(),
        'industries': get_industry_data(),
        'vix': get_vix_data(),
        'major_stocks': get_major_stocks(),
        'economic_indicators': get_economic_indicators(),
        'market_breadth': get_market_breadth(),
    }

    # Display summary
    logging.info("\n" + "="*60)
    logging.info("DATA SUMMARY")
    logging.info("="*60)

    if all_data['indices']:
        logging.info("\n📊 Market Indices:")
        for symbol, data in list(all_data['indices'].items())[:4]:
            logging.info(f"  {data['name']:30} ${data['price']:>10,.2f}  {data['changePercent']:>+8.2f}%")

    if all_data['sectors']:
        logging.info("\n🏢 Top Sectors:")
        sorted_sectors = sorted(all_data['sectors'].items(), key=lambda x: x[1]['changePercent'], reverse=True)[:3]
        for ticker, data in sorted_sectors:
            logging.info(f"  {data['name']:30} {data['changePercent']:>+8.2f}%")

    if all_data['vix']:
        logging.info(f"\n😨 Volatility: {all_data['vix']['price']} - {all_data['vix']['interpretation']}")

    # Export to JSON
    json_file = '/tmp/comprehensive_market_data.json'
    with open(json_file, 'w') as f:
        json.dump(all_data, f, indent=2)
    logging.info(f"\n✅ Complete data exported to {json_file}")

    # Also keep the original format for backwards compatibility
    legacy_file = '/tmp/latest_market_data.json'
    legacy_data = {
        'timestamp': all_data['timestamp'],
        'indices': all_data['indices'],
        'sectors': all_data['sectors'],
        'vix': all_data['vix'],
        'sp500_metrics': {}
    }
    with open(legacy_file, 'w') as f:
        json.dump(legacy_data, f, indent=2)

    logging.info(f"✅ Legacy format exported to {legacy_file}")
    logging.info(f"\n✅ DATA REFRESH COMPLETE - All pages ready with fresh data!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"❌ Fatal error: {e}")
        sys.exit(1)
