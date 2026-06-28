-- Migration 069: Fix ETF classification for JHDV and JVAL
-- Both are Janus Henderson ETFs leaking through the scores ETF filter because
-- stock_symbols.etf is not 'Y' and they are absent from etf_symbols.
-- Fix: add to etf_symbols and mark etf='Y' in stock_symbols.

INSERT INTO etf_symbols (symbol, security_name, asset_class)
VALUES
    ('JHDV', 'Janus Henderson U.S. Dividend Factor ETF', 'Equity'),
    ('JVAL', 'Janus Henderson U.S. Deep Value ETF', 'Equity')
ON CONFLICT (symbol) DO NOTHING;

UPDATE stock_symbols
SET etf = 'Y'
WHERE symbol IN ('JHDV', 'JVAL');
