-- Session 196: Deactivate removed ETFs in stock_symbols table
-- These ETFs were still marked as ACTIVE, causing load_prices.py to fetch them
-- even though DEFAULT_ESSENTIAL_ETF_SYMBOLS was updated.
-- get_active_symbols() reads all active symbols from stock_symbols, so we must
-- deactivate them here to prevent wasted yfinance API calls.

UPDATE stock_symbols SET active = FALSE
WHERE symbol IN ('XLK','XLF','XLV','XLY','XLC','XLI','XLP','XLE','XLU','XLRE','XLB','DIA','IVV','VXX');

-- Note: Only 13 symbols were found (VXX may not be in our symbol universe)
-- All sector ETFs (XLK-XLB) were successfully deactivated
