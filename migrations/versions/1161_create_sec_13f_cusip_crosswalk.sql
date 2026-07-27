-- Migration 1161: CUSIP->ticker crosswalk cache for SEC Form 13F institutional holdings
--
-- SEC's 13F INFOTABLE bulk dataset identifies securities by CUSIP only (never ticker -
-- see loaders/load_institutional_holdings_13f.py's module docstring). CUSIP itself is a
-- licensed identifier with no free SEC-published crosswalk, but OpenFIGI (Bloomberg's
-- free, public mapping API) can resolve a CUSIP to its real ticker/entity name.
--
-- CUSIP->ticker attribution is stable across quarters (changes only on M&A/ticker
-- changes/relisting), so this table caches OpenFIGI's resolution permanently. Without
-- it, every quarterly loader run would need to re-crosswalk the full ~34,000-CUSIP
-- universe (OpenFIGI's unauthenticated rate limit of 10 jobs/request, 25 requests/min
-- makes that a multi-hour cold run) instead of just the small quarterly delta of CUSIPs
-- never seen before.
--
-- ticker/resolved_name are NULL when OpenFIGI could not resolve the CUSIP at all - a
-- real, cacheable negative result (bond, private placement, foreign-only listing, etc.),
-- not an error. Whether a cached ticker is actually one of OUR tracked symbols (and
-- whether its name plausibly matches our own SEC entity_name - see
-- utils/external/openfigi_crosswalk.py's names_plausibly_match) is decided at read time,
-- not cached, so this table stays a pure "what does OpenFIGI think this CUSIP is"
-- record, independent of which symbols we currently track.

BEGIN;

CREATE TABLE IF NOT EXISTS sec_13f_cusip_crosswalk (
    cusip VARCHAR(9) PRIMARY KEY,
    ticker VARCHAR(20),
    resolved_name VARCHAR(255),
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sec_13f_cusip_crosswalk_ticker
    ON sec_13f_cusip_crosswalk (ticker)
    WHERE ticker IS NOT NULL;

COMMIT;
