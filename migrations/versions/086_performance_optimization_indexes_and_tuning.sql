-- Migration 086: Performance optimization - Indexes and loader tuning
-- Addresses issues #36-40 from performance audit
-- ════════════════════════════════════════════════════════════════════════════

-- Issue #36: Optimize signal_quality_scores watermark query (per-symbol loader)
-- Current: idx_signal_quality_scores_symbol_date(symbol, date) doesn't include DESC
-- Problem: Watermark queries need MAX(date) per symbol, DESC ordering helps
-- Solution: Add covering index with DESC on date for efficient watermark lookups
-- Note: Existing idx_signal_quality_scores_symbol_date will remain for compatibility
CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_symbol_date_desc
ON signal_quality_scores(symbol, date DESC)
WHERE date IS NOT NULL;

-- Issue #37: Add index for Phase 5 signal generation filtering
-- Current: No index on (date, signal_type)
-- Problem: Phase 5 filters by date and signal_type sequentially, causing full table scan
-- Solution: Covering index for fast signal type filtering by date
-- Phase 5 uses: SELECT * FROM buy_sell_daily WHERE date = ? AND signal_type = ?
CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_date_signal_type
ON buy_sell_daily(date, signal_type)
WHERE signal_type IS NOT NULL;

-- Issue #38: Dashboard N+1 query mitigation (covered by application changes)
-- Pre-index common dashboard filters to reduce query latency
-- Covers common patterns like: WHERE date = ? AND signal = ?
CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_date_signal
ON buy_sell_daily(date, signal)
WHERE signal IS NOT NULL;

-- Support for signal_quality_scores dashboard lookups (ranking/scoring)
-- Covers common patterns: WHERE date = ? ORDER BY composite_sqs DESC
CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_date_composite_sqs
ON signal_quality_scores(date DESC, composite_sqs DESC)
WHERE composite_sqs IS NOT NULL;

-- Analyze the tables to update planner statistics
ANALYZE signal_quality_scores;
ANALYZE buy_sell_daily;
