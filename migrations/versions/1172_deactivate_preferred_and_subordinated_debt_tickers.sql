-- Migration 1172: deactivate preferred-share/subordinated-debt tickers that slipped past
-- load_market_constituents.py's EXCLUSION_PATTERNS (see that file's 2026-07-28 governance
-- comment for the full list of missed phrasings: "Preference Shares", "Subordinated
-- Debentures"/"Notes", "Pfd Ser"/"Pfd Stock"). These are junior debt/preferred-equity
-- instruments, not common stock - they were flowing through technical
-- indicators/scoring/signal generation as if they were ordinary tradeable equities.
--
-- Live-verified before this migration: zero of these 58 symbols have any row in
-- algo_positions or algo_trades (no open positions, no trade history at risk).
-- BHFAL has 5 historical buy_sell_daily signal rows but never actually traded.
--
-- Deliberately NOT touching BNS ("Bank Nova Scotia Halifax Pfd 3 Ordinary Shares") - a
-- real, actively-traded common ADR (Bank of Nova Scotia / Scotiabank) with a garbled
-- security_name in the raw NASDAQ feed that happens to contain "Pfd", live-confirmed via
-- real price_daily volume (~1-4M shares/day) matching known BNS trading behavior.
--
-- Uses the existing `active` column (get_active_symbols() already filters
-- `WHERE active = true` - utils/loaders/helpers.py) rather than a hard delete, so this is
-- reversible and preserves any historical rows in other tables keyed by these symbols.

BEGIN;

UPDATE stock_symbols
SET active = false
WHERE symbol IN (
    'AFGB', 'AFGC', 'AFGD', 'AFGE', 'AHL$D', 'AHL$E', 'AHL$F', 'ALL$B',
    'ATH$A', 'ATH$B', 'ATH$D', 'ATH$E', 'ATHS', 'BAC$E', 'BAC$L', 'BEPH',
    'BEPI', 'BEPJ', 'BHFAL', 'BIPI', 'BNJ', 'CNO$A', 'DCBG', 'DTB', 'DTG',
    'DTK', 'DTW', 'DUKB', 'FITB$I', 'GAB$H', 'GGN$B', 'GL$D', 'GS$D',
    'KMPB', 'LILAP', 'MS$A', 'NEE$N', 'NEE$U', 'NEE$W', 'RNR$F', 'RNR$G',
    'RZC', 'SCE$M', 'SCE$N', 'TRTN$A', 'TRTN$B', 'TRTN$C', 'TRTN$D',
    'TRTN$E', 'TRTN$F', 'TRTN$G', 'USB$A', 'USB$H', 'VNO$L', 'WRB$E',
    'WRB$F', 'WRB$G', 'WRB$H'
)
AND active = true;

COMMIT;
