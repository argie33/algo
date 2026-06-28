-- Migration 099: Create ad_line_daily table for advance/decline line tracking
-- Description: Stores advance-decline line direction for market breadth confirmation
-- This table is CRITICAL for market_exposure calculation (6 points)
-- Created: 2026-06-28

CREATE TABLE IF NOT EXISTS ad_line_daily (
    date DATE NOT NULL PRIMARY KEY,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('up', 'down')),
    advances INTEGER,
    declines INTEGER,
    advance_decline_ratio NUMERIC(10, 4),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_ad_line_date ON ad_line_daily(date DESC);
CREATE INDEX IF NOT EXISTS idx_ad_line_direction ON ad_line_daily(direction);
