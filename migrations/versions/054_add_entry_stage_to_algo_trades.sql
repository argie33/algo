-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION 054: Add entry_stage column to algo_trades table
-- ════════════════════════════════════════════════════════════════════════════
-- Issue: #4 Missing Database Columns
-- Purpose: Track the market stage (Minervini/Weinstein) at trade entry for analysis
--
-- The entry_stage column captures the market state when the trade was entered,
-- enabling portfolio-level analysis of which market stages yielded the best returns.

ALTER TABLE algo_trades
ADD COLUMN IF NOT EXISTS entry_stage VARCHAR(20);

-- Index for performance when filtering/grouping by entry_stage
CREATE INDEX IF NOT EXISTS idx_algo_trades_entry_stage
ON algo_trades(entry_stage) WHERE entry_stage IS NOT NULL;
