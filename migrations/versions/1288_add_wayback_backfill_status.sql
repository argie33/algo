-- Migration 1288: Add wayback_backfill_status - tracks per-symbol attempts to backfill
-- historical delisted-security prices scraped from the Wayback Machine's archived captures of
-- old Yahoo Finance pages (finance.yahoo.com/q/hp and ichart.finance.yahoo.com/table.csv), for
-- scripts/wayback_yahoo_delisted_price_backfill.py.
--
-- Companion to tiingo_backfill_status (migration 1282): Tiingo's free tier only reaches back to
-- ~2015-era delistings (SIVB/SBNY confirmed, but Lehman/Enron/WorldCom/Bear Stearns/WaMu
-- confirmed absent even there). This is a zero-cost, no-daily-quota source that can reach much
-- older history because Yahoo's now-dead ichart.finance.yahoo.com/table.csv and finance.yahoo.
-- com/q/hp endpoints were spot-archived by real crawls/users going back to ~1999, including
-- point-in-time captures taken during and immediately after several of these companies'
-- collapses (e.g. a real 2008-12-18 capture of Lehman's post-bankruptcy LEHMQ.PK ticker showing
-- $0.03-0.04/share pink-sheet trades, confirmed live this session).
--
-- resolved_ticker records any ticker-change Yahoo itself reported while resolving a symbol
-- (e.g. LEH -> LEHMQ.PK) so a re-run doesn't have to re-discover the chain from scratch.

CREATE TABLE IF NOT EXISTS wayback_backfill_status (
    symbol VARCHAR(20) PRIMARY KEY,
    status VARCHAR(30) NOT NULL CHECK (status IN ('backfilled', 'no_data_at_vendor', 'error')),
    rows_inserted INTEGER NOT NULL DEFAULT 0,
    resolved_ticker VARCHAR(20),
    last_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detail VARCHAR(500)
);
