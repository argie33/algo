-- Migration 067: Add index on signal_quality_scores(created_at DESC)
-- The /api/health basic check queries MAX(created_at) which causes a full table scan,
-- timing out at 3000ms every 5 minutes. An index on created_at lets postgres satisfy
-- both ORDER BY ... DESC LIMIT 1 and MAX(created_at) instantly.

CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_created_at
ON signal_quality_scores (created_at DESC);

ANALYZE signal_quality_scores;
