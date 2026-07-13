-- Migration 1105: Fix swing_weight_* config values stored as fractions instead of int percentages
--
-- CONTEXT: All 7 swing_weight_* keys in algo_config are stored as float fractions
-- (0.05-0.25, summing to 1.0) with value_type='float'. Every consumer of these keys
-- (algo/infrastructure/config_schema.py's VALIDATION_SCHEMA, algo/infrastructure/
-- config/main.py's DEFAULTS, and algo/orchestration/weight_optimizer.py's
-- get_current_weights()/apply()) expects an int percentage (0-100, summing to 100).
--
-- Concretely broken because of this drift: AlgoConfig.get() detects the type mismatch
-- (schema says "int", stored value is a float string) and returns None instead of the
-- stored value. WeightOptimizer.get_current_weights() then raises
-- "Weight config key 'swing_weight_setup' for component 'setup_quality' returned None",
-- which crashes Phase 9 (reconciliation) on every orchestrator run — confirmed live in
-- AWS via /api/algo/status on 2026-07-13.
--
-- This is a genuine, intentional weight distribution (not the DEFAULTS values -- e.g.
-- setup=0.15 here vs DEFAULTS setup=25/100), just stored in the wrong unit/type. Fix
-- re-expresses the same distribution as int percentages (value * 100) rather than
-- discarding it by resetting to DEFAULTS.

UPDATE algo_config SET value = '10', value_type = 'int' WHERE key = 'swing_weight_fundamentals' AND value_type = 'float';
UPDATE algo_config SET value = '20', value_type = 'int' WHERE key = 'swing_weight_momentum' AND value_type = 'float';
UPDATE algo_config SET value = '5', value_type = 'int' WHERE key = 'swing_weight_multi_timeframe' AND value_type = 'float';
UPDATE algo_config SET value = '10', value_type = 'int' WHERE key = 'swing_weight_sector' AND value_type = 'float';
UPDATE algo_config SET value = '15', value_type = 'int' WHERE key = 'swing_weight_setup' AND value_type = 'float';
UPDATE algo_config SET value = '25', value_type = 'int' WHERE key = 'swing_weight_trend' AND value_type = 'float';
UPDATE algo_config SET value = '15', value_type = 'int' WHERE key = 'swing_weight_volume' AND value_type = 'float';
