import yfinance as yf

# Test a few tickers
tickers = ['JCSE', 'JCTC', 'JDZG', 'JEM']

for ticker_sym in tickers:
    try:
        ticker = yf.Ticker(ticker_sym)
        result = ticker.upgrades_downgrades
        if result is None or result.empty:
            print(f"{ticker_sym}: No data available")
        else:
            print(f"{ticker_sym}: {len(result)} rows")
    except Exception as e:
        print(f"{ticker_sym}: Error - {type(e).__name__}: {str(e)}")
