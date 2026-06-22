-- Migration 094: Add phase7_min_composite_score config key
-- phase7_signal_generation.py requires this key to be present in algo_config.
-- Default 50 matches _MIN_COMPOSITE_SCORE constant in the phase7 module.

INSERT INTO algo_config (key, value, description, updated_by)
VALUES
    ('phase7_min_composite_score', '50', 'Minimum composite score (0-100) for a signal to qualify in Phase 7 signal generation', 'migration-094')
ON CONFLICT (key) DO NOTHING;
