-- Migration 1116: Backfill NULL rank_4w_ago / rank_12w_ago in sector_ranking
-- (and rank_4w_ago in industry_ranking)
--
-- ISSUE: load_sector_rankings.py only ever wrote rank_1w_ago; nothing in the codebase
-- writes rank_4w_ago / rank_12w_ago (migration 1101 seeded them once, but every row
-- written since has NULLs). algo/signals/sector_rotation.py hard-requires all three
-- lookback ranks non-NULL and skips any sector missing them — with ALL sectors skipped
-- it raises "No sector ranking data found", which fails MarketExposure.compute(), which
-- writes a NULL-regime data_unavailable marker to market_exposure_daily, which makes
-- /api/algo/markets return 503 and blocks risk-tier position sizing. Confirmed live
-- 2026-07-14 via /ecs/algo-market_exposure_daily-loader CloudWatch logs (every sector:
-- "missing 4w, 12w data for 2026-07-13").
--
-- The loader is fixed in the same commit to write all three lookbacks (nearest prior
-- row at-or-before the lookback date, bootstrapping to current_rank when no history —
-- the same neutral-momentum bootstrap the 1w column has always used). This migration
-- applies that bootstrap to existing rows so the current eval date works immediately.

ALTER TABLE sector_ranking ADD COLUMN IF NOT EXISTS rank_4w_ago INTEGER;
ALTER TABLE sector_ranking ADD COLUMN IF NOT EXISTS rank_12w_ago INTEGER;
ALTER TABLE industry_ranking ADD COLUMN IF NOT EXISTS rank_4w_ago INTEGER;

UPDATE sector_ranking
SET rank_1w_ago = COALESCE(rank_1w_ago, current_rank),
    rank_4w_ago = COALESCE(rank_4w_ago, current_rank),
    rank_12w_ago = COALESCE(rank_12w_ago, current_rank)
WHERE rank_1w_ago IS NULL OR rank_4w_ago IS NULL OR rank_12w_ago IS NULL;

UPDATE industry_ranking
SET rank_1w_ago = COALESCE(rank_1w_ago, current_rank),
    rank_4w_ago = COALESCE(rank_4w_ago, current_rank)
WHERE rank_1w_ago IS NULL OR rank_4w_ago IS NULL;
