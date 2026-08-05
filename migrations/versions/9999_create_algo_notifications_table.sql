-- Migration: Create algo_notifications table for alert persistence
-- Date: 2026-08-05
-- Context: Alert system requires persistent storage for all notifications regardless of
--          email/SNS configuration. Table persists to DB even if external channels unavailable.

CREATE TABLE IF NOT EXISTS algo_notifications (
    id SERIAL PRIMARY KEY,
    kind VARCHAR(100) NOT NULL,
    severity VARCHAR(50) NOT NULL,
    title VARCHAR(255),
    message TEXT,
    symbol VARCHAR(20),
    details JSONB,
    seen BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_algo_notifications_created_at ON algo_notifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_algo_notifications_severity ON algo_notifications(severity);
CREATE INDEX IF NOT EXISTS idx_algo_notifications_kind ON algo_notifications(kind);
CREATE INDEX IF NOT EXISTS idx_algo_notifications_seen ON algo_notifications(seen) WHERE seen = FALSE;

-- Verification
SELECT 'algo_notifications table ready for alert persistence' as status;
