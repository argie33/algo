-- Migration 070: Clean ETF records from stock_scores
-- Remove any ETF records that shouldn't be in stock_scores table.
-- ETFs should only be in etf_symbols table, not stock_scores.

DELETE FROM stock_scores
WHERE symbol IN (SELECT symbol FROM etf_symbols);

-- Also mark any remaining ETFs in stock_symbols as etf='Y' if they're in etf_symbols
UPDATE stock_symbols
SET etf = 'Y'
WHERE symbol IN (SELECT symbol FROM etf_symbols)
  AND (etf IS NULL OR etf != 'Y');

-- Ensure all stocks in stock_symbols are marked etf='N' if not already
UPDATE stock_symbols
SET etf = 'N'
WHERE etf IS NULL
  AND symbol NOT IN (SELECT symbol FROM etf_symbols);
