-- Migration 1180: Add top_10_institutions_pct to institutional_holdings_13f
--
-- ISSUE: positioning_metrics.institutional_holders_count and .top_10_institutions_pct were
-- both hardcoded None for 100% of symbols (5486/5486) in load_positioning_metrics.py, with
-- the comment "requires enhanced 13F data extraction not yet implemented". Root cause:
-- load_institutional_holdings_13f.py's bulk INFOTABLE.tsv parse collapsed shares straight to
-- a per-CUSIP total (holdings_by_cusip[cusip] += shares), discarding the per-manager
-- (ACCESSION_NUMBER) identity needed to count distinct holders or compute concentration.
-- institutional_holdings_13f.number_of_institutional_holders already existed as a column but
-- was likewise always written as a literal None.
--
-- FIX: the loader now additionally tracks per-manager shares (bounded to CUSIPs already
-- known to resolve to our tracked universe, to keep memory bounded - see
-- _get_known_tracked_cusips()/_fetch_and_parse_13f_bulk()'s docstrings) and computes real
-- holder counts and top-10-by-shares concentration. This migration adds the one missing
-- column; number_of_institutional_holders already existed and just needed real data.

ALTER TABLE institutional_holdings_13f ADD COLUMN IF NOT EXISTS top_10_institutions_pct NUMERIC(6, 2);

COMMENT ON COLUMN institutional_holdings_13f.top_10_institutions_pct IS
    'Percent of total institutional shares held by the top 10 institutional managers (by ACCESSION_NUMBER-level shares from the SEC 13F INFOTABLE bulk dataset). Only populated for CUSIPs already resolved to a tracked ticker in a prior run - see load_institutional_holdings_13f.py.';
COMMENT ON COLUMN institutional_holdings_13f.number_of_institutional_holders IS
    'Count of distinct institutional managers (by ACCESSION_NUMBER) reporting a holding in this symbol via SEC 13F. Previously always NULL (never implemented); now computed the same way as top_10_institutions_pct.';
