-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION 036: Create Market Exposure Tiers Configuration Table
-- Purpose: Consolidate duplicated hardcoded tier definitions from two API endpoints
-- References: ARCHITECTURAL_AUDIT_CALCULATIONS.md violation #2
-- ════════════════════════════════════════════════════════════════════════════

-- Market Exposure Tiers: Configuration for market tier assignment and risk rules
-- This table consolidates duplicate definitions in:
--   1. algo.js /markets endpoint (lines 834-851)
--   2. algo.js /exposure-policy endpoint (lines 1163-1193)
CREATE TABLE IF NOT EXISTS market_exposure_tiers (
    tier_id SERIAL PRIMARY KEY,
    tier_name VARCHAR(100) NOT NULL UNIQUE,
    tier_description TEXT,

    -- Exposure range (determines which tier applies)
    min_exposure_pct NUMERIC(8, 2) NOT NULL,
    max_exposure_pct NUMERIC(8, 2) NOT NULL,

    -- Risk management settings
    risk_multiplier NUMERIC(8, 4) NOT NULL,         -- Applied to position size calculations
    max_new_positions INT NOT NULL,                 -- Maximum new positions allowed today
    min_swing_score INT NOT NULL,                   -- Minimum entry score requirement
    min_swing_grade VARCHAR(10) DEFAULT 'B',        -- Minimum grade letter

    -- Strict rules for this tier
    halt_new_entries BOOLEAN DEFAULT FALSE,         -- If true, no new entries allowed
    force_exit_negative_r BOOLEAN DEFAULT FALSE,    -- If true, force exits on losing positions

    -- Partial exit rules (if not null, apply these rules)
    tighten_winners_at_r NUMERIC(8, 2),            -- Tighten stops on winners at this R multiple
    force_partial_at_r NUMERIC(8, 2),              -- Force partial exit at this R multiple

    -- Display settings
    display_color VARCHAR(50),                      -- UI color (green, lightgreen, yellow, orange, red)
    display_order INT DEFAULT 0,                    -- Sort order in API responses

    -- Version control
    version INT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    notes TEXT
);

-- Index for fast tier lookup by exposure range
CREATE INDEX IF NOT EXISTS idx_market_exposure_tiers_range
ON market_exposure_tiers(min_exposure_pct, max_exposure_pct)
WHERE is_active;

-- Index for active tier lookup by name
CREATE INDEX IF NOT EXISTS idx_market_exposure_tiers_name
ON market_exposure_tiers(tier_name)
WHERE is_active;

-- Seed initial tier configuration from current hardcoded values in algo.js
INSERT INTO market_exposure_tiers (
    tier_name, tier_description,
    min_exposure_pct, max_exposure_pct,
    risk_multiplier, max_new_positions, min_swing_score, min_swing_grade,
    halt_new_entries, force_exit_negative_r,
    tighten_winners_at_r, force_partial_at_r,
    display_color, display_order,
    is_active, updated_by, notes
) VALUES
    -- Tier 1: Confirmed Uptrend (80-100% exposure)
    ('confirmed_uptrend', 'Healthy bull market — full deployment',
     80, 100, 1.0, 5, 60, 'B',
     FALSE, FALSE, NULL, NULL,
     'green', 5,
     TRUE, 'migration', 'Initial seed from algo.js /markets endpoint'),

    -- Tier 2: Healthy Uptrend (60-80% exposure)
    ('healthy_uptrend', 'Bull market with caution — slightly reduced risk',
     60, 80, 0.85, 4, 65, 'B',
     FALSE, FALSE, 3.0, NULL,
     'lightgreen', 4,
     TRUE, 'migration', 'Initial seed from algo.js /markets endpoint'),

    -- Tier 3: Pressure (40-60% exposure)
    ('pressure', 'Uptrend under pressure — defensive posture',
     40, 60, 0.5, 2, 70, 'A',
     FALSE, FALSE, 2.0, 3.0,
     'yellow', 3,
     TRUE, 'migration', 'Initial seed from algo.js /markets endpoint'),

    -- Tier 4: Caution (20-40% exposure)
    ('caution', 'Major caution — entries halted unless exceptional',
     20, 40, 0.25, 1, 75, 'A',
     TRUE, FALSE, 1.5, 2.0,
     'orange', 2,
     TRUE, 'migration', 'Initial seed from algo.js /markets endpoint'),

    -- Tier 5: Correction (0-20% exposure)
    ('correction', 'Market correction — preserve capital',
     0, 20, 0.0, 0, 100, 'A+',
     TRUE, TRUE, 1.0, 1.5,
     'red', 1,
     TRUE, 'migration', 'Initial seed from algo.js /markets endpoint')
ON CONFLICT (tier_name) DO NOTHING;

-- Add reference column to market_exposure_daily to link to tier configuration
ALTER TABLE market_exposure_daily ADD COLUMN IF NOT EXISTS active_tier_id INT
    REFERENCES market_exposure_tiers(tier_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_market_exposure_daily_tier_id
ON market_exposure_daily(active_tier_id);

-- Backfill active_tier_id for historical records based on exposure_pct
UPDATE market_exposure_daily med
SET active_tier_id = (
    SELECT tier_id FROM market_exposure_tiers
    WHERE is_active = TRUE
    AND med.exposure_pct >= min_exposure_pct
    AND med.exposure_pct <= max_exposure_pct
    LIMIT 1
)
WHERE active_tier_id IS NULL AND exposure_pct IS NOT NULL;

-- Track this migration in data_loader_status
INSERT INTO data_loader_status (
    table_name, status, row_count, latest_date, age_days, checked_at
) VALUES (
    'market_exposure_tiers', 'MANUAL_CONFIG', 5, CURRENT_DATE, 0, CURRENT_TIMESTAMP
) ON CONFLICT (table_name) DO UPDATE SET
    row_count = (SELECT COUNT(*) FROM market_exposure_tiers WHERE is_active),
    checked_at = CURRENT_TIMESTAMP;
