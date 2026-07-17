-- Session 196: Remove wasteful ETF data
-- Removes 14 ETFs that were never used by any algorithm:
-- - Sector ETFs (XLK, XLF, XLV, XLY, XLC, XLI, XLP, XLE, XLU, XLRE, XLB): Sector performance computed from stock_scores instead
-- - Low-value ETFs (DIA, IVV, VXX): Redundant or unused
-- Impact: Saves 3,500 yfinance API calls/year, ~4,500 rows of storage, zero functional loss
--
-- Kept essential ETFs: SPY, QQQ, IWM, GLD, TLT (5 symbols)
-- See ETF_USAGE_ANALYSIS.md for complete analysis

DELETE FROM etf_price_daily
WHERE symbol IN ('XLK','XLF','XLV','XLY','XLC','XLI','XLP','XLE','XLU','XLRE','XLB','DIA','IVV','VXX');

DELETE FROM etf_price_weekly
WHERE symbol IN ('XLK','XLF','XLV','XLY','XLC','XLI','XLP','XLE','XLU','XLRE','XLB','DIA','IVV','VXX');

DELETE FROM etf_price_monthly
WHERE symbol IN ('XLK','XLF','XLV','XLY','XLC','XLI','XLP','XLE','XLU','XLRE','XLB','DIA','IVV','VXX');
