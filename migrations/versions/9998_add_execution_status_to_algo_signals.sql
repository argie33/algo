-- Migration: Add execution_status column to algo_signals
-- Purpose: Track whether a signal was executed, rejected, pending, or expired
-- Rationale: Current design inserts signals as "active" then rejects them, but never updates the record
--           This leaves rejected signals marked as active in the database, causing dashboard confusion

-- Add execution_status column
ALTER TABLE algo_signals
ADD COLUMN execution_status VARCHAR(50) DEFAULT 'pending'
CONSTRAINT valid_execution_status CHECK (execution_status IN ('pending', 'executed', 'rejected', 'expired'));

-- Add rejection_reason column (mirrors algo_signal_rejections.rejection_stage for quick lookup)
ALTER TABLE algo_signals
ADD COLUMN rejection_reason VARCHAR(200);

-- Create index on execution_status for fast dashboard queries
CREATE INDEX idx_algo_signals_execution_status
ON algo_signals(execution_status, signal_date DESC);

-- Backfill: Signals that executed (have corresponding algo_trades) → execution_status='executed'
UPDATE algo_signals s
SET execution_status = 'executed'
WHERE EXISTS (
  SELECT 1 FROM algo_trades t
  WHERE t.symbol = s.symbol
  AND DATE(t.created_at) = s.signal_date
  AND t.status IN ('open', 'filled', 'closed')
);

-- Backfill: Signals with rejection reasons (from algo_signal_rejections) → execution_status='rejected'
UPDATE algo_signals s
SET execution_status = 'rejected',
    rejection_reason = (
      SELECT rejection_stage || ': ' || SUBSTRING(rejection_reason, 1, 150)
      FROM algo_signal_rejections r
      WHERE r.symbol = s.symbol
      AND r.rejection_date = s.signal_date
      ORDER BY r.created_at DESC
      LIMIT 1
    )
WHERE EXISTS (
  SELECT 1 FROM algo_signal_rejections r
  WHERE r.symbol = s.symbol
  AND r.rejection_date = s.signal_date
);

-- Backfill: Signals older than 7 days without an execution status → execution_status='expired'
UPDATE algo_signals
SET execution_status = 'expired'
WHERE execution_status = 'pending'
AND signal_date < CURRENT_DATE - INTERVAL '7 days';

-- Leave remaining pending as-is
-- Note: Stale backlog (pending from >7d ago) indicates Phase 8 didn't process, likely due to halt flag or data issues

-- Verification queries (run after migration):
-- SELECT execution_status, COUNT(*) FROM algo_signals WHERE signal_date >= CURRENT_DATE - 7 GROUP BY execution_status;
-- SELECT symbol, execution_status, rejection_reason FROM algo_signals WHERE signal_date >= CURRENT_DATE - 1 AND execution_status='rejected' LIMIT 10;
