CREATE TABLE IF NOT EXISTS signal_filter_tiers (
    tier_id SERIAL PRIMARY KEY,
    tier_name VARCHAR(100) NOT NULL UNIQUE,
    tier_description TEXT,
    completeness_pct_min NUMERIC(8, 2) NOT NULL,
    trend_score_min INT NOT NULL,
    sqs_min INT NOT NULL,
    require_all_tiers BOOLEAN DEFAULT TRUE,
    max_qualified_signals INT DEFAULT 12,
    sort_by VARCHAR(50) DEFAULT 'sqs',
    sort_order VARCHAR(10) DEFAULT 'DESC',
    version INT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_signal_filter_tiers_active
ON signal_filter_tiers(is_active, tier_name);

INSERT INTO signal_filter_tiers (
    tier_name, tier_description,
    completeness_pct_min, trend_score_min, sqs_min,
    require_all_tiers, max_qualified_signals, sort_by, sort_order,
    is_active, updated_by, notes
) VALUES (
    'default_signal_filter_v1',
    'Default signal filter configuration from algo.js',
    45,
    8,
    40,
    TRUE,
    12,
    'sqs',
    'DESC',
    TRUE,
    'migration',
    'Initial seed from hardcoded values'
) ON CONFLICT (tier_name) DO NOTHING;
