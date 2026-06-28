-- Migration 081: Update max_positions from 12 to 15
-- Increases the maximum concurrent positions allowed by the algo.

UPDATE algo_config
SET value = '15', updated_by = 'migration-081', updated_at = CURRENT_TIMESTAMP
WHERE key = 'max_positions' AND value = '12';
