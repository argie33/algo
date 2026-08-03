-- Migration 1181: deactivate SPAC rights offerings, when-issued shares, and bare
-- "X% Series Y"/depositary-share preferred tickers that slipped past
-- load_market_constituents.py's EXCLUSION_PATTERNS (see that file's 2026-08-03 governance
-- comment for the full list of missed phrasings). Follow-up to migration 1172, which
-- covered a different set of missed preferred/subordinated-debt phrasings.
--
-- Root-caused while investigating price_daily's chronic ~4% "missing symbol" completion
-- gap: yfinance has no ticker at all for most of these instrument types, so they
-- permanently failed every price-loader run while silently counting against the
-- completion threshold (0/5486 possible, forever).
--
-- Live-verified before this migration: zero of these 28 symbols have any row in
-- algo_positions, algo_trades, or buy_sell_daily (no open positions, no trade history,
-- no signal history at risk).
--
-- Deliberately NOT touching SCE$L ("SCE TRUST VI" - ambiguous, no distinguishing
-- preferred/rights keyword, a bare `\btrust\b` pattern would risk false-positiving real
-- REIT common stock) or MKC.V ("McCormick & Company, Incorporated Common Stock" - a real
-- common stock with an unusual ticker suffix, a symbol-table data-hygiene question, not
-- an instrument-type exclusion). Both left active pending individual review.
--
-- Uses the existing `active` column (get_active_symbols() already filters
-- `WHERE active = true` - utils/loaders/helpers.py) rather than a hard delete, so this is
-- reversible and preserves any historical rows in other tables keyed by these symbols.

BEGIN;

UPDATE stock_symbols
SET active = false
WHERE symbol IN (
    'AIIA.R', 'JENA.R', 'VECA.R', 'REZI.V', 'ADIG.V', 'CELG.R', 'DGAC.R',
    'DBRG$H', 'DBRG$I', 'DBRG$J', 'EPR$E', 'EQH$A', 'GLED.R', 'JACS.R',
    'MET$E', 'MS$F', 'NLY$F', 'OTAI.R', 'PLUN.R', 'QRED.R', 'SAGU.R',
    'SOUL.R', 'STT$G', 'TFC$I', 'TRAD.R', 'WENC.R', 'WPAC.R', 'XFLH.R'
)
AND active = true;

COMMIT;
