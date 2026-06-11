-- Migration 003: Create Signal Filter Tiers Configuration Table
-- Purpose: Move hardcoded signal filtering thresholds from API to database
-- References: ARCHITECTURAL_AUDIT_CALCULATIONS.md violation #1

-- Signal Filter Tiers: Configuration for signal evaluation and filtering rules
-- This table replaces hardcoded thresholds in algo.js /evaluate endpoint
CREATE TABLE IF NOT EXISTS signal_filter_tiers (
    tier_id SERIAL PRIMARY KEY,
    tier_name VARCHAR(100) NOT NULL UNIQUE,
    tier_description TEXT,

    -- Filter thresholds (business rules)
    completeness_pct_min NUMERIC(8, 2) NOT NULL,  -- Minimum data completeness %
    trend_score_min INT NOT NULL,                  -- Minimum trend score
    sqs_min INT NOT NULL,                          -- Minimum Signal Quality Score

    -- Combination logic
    require_all_tiers BOOLEAN DEFAULT TRUE,        -- If true, ALL tiers must pass; if false, ANY

    -- Ranking and selection
    max_qualified_signals INT DEFAULT 12,          -- Maximum number of signals to return as "top qualified"
    sort_by VARCHAR(50) DEFAULT 'sqs',             -- Field to sort by (sqs, trend_score, completeness_pct)
    sort_order VARCHAR(10) DEFAULT 'DESC',         -- ASC or DESC

    -- Version control
    version INT DEFAULT 1,                          -- Increment when rules change
    is_active BOOLEAN DEFAULT TRUE,                 -- Soft delete: mark old versions as inactive
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    notes TEXT                                      -- Reason for changes (e.g., "Adjusted based on session 31 analysis")
);

-- Index for fast tier lookup by name and active status
CREATE INDEX IF NOT EXISTS idx_signal_filter_tiers_active
ON signal_filter_tiers(is_active, tier_name);

-- Seed initial tier configuration from current hardcoded values in algo.js
INSERT INTO signal_filter_tiers (
    tier_name, tier_description,
    completeness_pct_min, trend_score_min, sqs_min,
    require_all_tiers, max_qualified_signals, sort_by, sort_order,
    is_active, updated_by, notes
) VALUES (
    'default_signal_filter_v1',
    'Default signal filter configuration from algo.js /evaluate endpoint',
    45,      -- tier1: completeness_pct >= 45
    8,       -- tier3: trend_score >= 8
    40,      -- tier4: sqs >= 40
    TRUE,    -- require_all_tiers (matches: all_tiers_pass = tier1 && tier3 && tier4)
    12,      -- max_qualified_signals (hardcoded slice(0, 12))
    'sqs',   -- sort_by (current behavior: sorted by sqs)
    'DESC',  -- sort_order
    TRUE,
    'migration',
    'Initial seed from hardcoded values in algo.js:196-215'
) ON CONFLICT (tier_name) DO NOTHING;

-- Track this migration in data_loader_status
INSERT INTO data_loader_status (
    table_name, status, row_count, latest_date, age_days, checked_at
) VALUES (
    'signal_filter_tiers', 'MANUAL_CONFIG', 1, CURRENT_DATE, 0, CURRENT_TIMESTAMP
) ON CONFLICT (table_name) DO UPDATE SET
    row_count = (SELECT COUNT(*) FROM signal_filter_tiers WHERE is_active),
    checked_at = CURRENT_TIMESTAMP;
