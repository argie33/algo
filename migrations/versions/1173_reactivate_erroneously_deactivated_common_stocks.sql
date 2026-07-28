-- Migration 1173: reactivate 15 real, currently-tradeable common stocks that were
-- erroneously marked active=false in this local dev DB, with zero recorded reason and
-- no current code path in the repo that sets stock_symbols.active=false other than
-- migration 1122 (a hardcoded list of 13 specific sector ETF tickers - none of which
-- overlap this list) and migration 1172 (this session's own preferred/subordinated-debt
-- cleanup, also non-overlapping). Found live 2026-07-28 while auditing stock_symbols.active
-- for the preferred-share cleanup above: these 15 symbols include NVIDIA Corporation
-- itself (NVDA) - one of the largest, most liquid stocks in the market - completely
-- excluded from get_active_symbols() (utils/loaders/helpers.py's `WHERE active = true`
-- filter) and therefore from technical indicators, scoring, and signal generation.
--
-- All 15 have substantial real price_daily history through 2026-07-23 (270-1301 rows
-- each, same recent cutoff as the rest of the universe) - confirming none are actually
-- delisted or otherwise legitimately excluded; this is stale local data drift (most
-- likely leftover manual/experimental DB state from a prior debugging session), not a
-- live bug to chase in code. Deactivated at exactly 2 batch timestamps
-- (2026-07-19 14:20:53 and 2026-07-20 06:29:38), consistent with 2 one-off manual
-- UPDATE statements rather than any recurring scheduled process.
--
-- NOTE: this is a local-dev-only data correction. There is no way to confirm from this
-- environment whether production's stock_symbols table has the same drift - if so, this
-- migration's UPDATE is safe to apply there too (idempotent, symbol-scoped), but that
-- needs separate verification against the real production DB.

BEGIN;

UPDATE stock_symbols
SET active = true
WHERE symbol IN (
    'ESEA', 'INCY', 'JCAP', 'NVDA', 'PDLB', 'XNET', 'CNA', 'ING',
    'TD', 'TGS', 'TRNO', 'CP', 'BCAL', 'GAIN', 'HG'
)
AND active = false;

COMMIT;
