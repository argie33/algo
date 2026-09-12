-- Migration 1286: Retract remaining stale dividend_data fetch_error/cik_not_found markers
--
-- Follow-up to migration 1214 (2026-08-20), which cleaned up the one-time backlog of
-- spurious data_unavailable marker rows coexisting with real dividend history for the
-- same symbol. That migration was a one-off cleanup; load_dividend_data.py's success path
-- (fetch_incremental's `if unique_results: return unique_results`, and the custom-extension
-- fallback branch) never called `_retract_stale_marker()` after successfully extracting real
-- data, only the two failure branches did (cik_not_found, fetch_error - both fixed
-- 2026-08-21). So a symbol that had an old marker row from before those fixes, and later
-- succeeded normally here, kept its stale marker forever - nothing else ever revisited it.
--
-- Live-confirmed 2026-09-12 ("Other (errors/excluded)" bucket audit): 13 such symbols still
-- coexisting post-1214. Code fix (same change, loaders/load_dividend_data.py) now retracts
-- the marker on every successful-extraction path too, closing the loop. This migration only
-- cleans the already-accumulated residual - same criteria as 1214.

DELETE FROM dividend_data d
WHERE d.data_unavailable = TRUE
  AND d.dividend_per_share IS NULL
  AND EXISTS (
        SELECT 1 FROM dividend_data d2
        WHERE d2.symbol = d.symbol AND d2.dividend_per_share IS NOT NULL
      );
