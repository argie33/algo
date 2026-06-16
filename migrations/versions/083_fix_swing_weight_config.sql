-- Migration 083: Fix swing_weight_* config values that were set to 0
-- The ON CONFLICT DO NOTHING seeding left them at 0 if previously inserted wrong.
-- Correct weights must sum to 100: setup(25) + trend(20) + momentum(20) + volume(12) +
-- fundamentals(10) + sector(8) + multi_timeframe(5) = 100.

UPDATE algo_config SET value = '25' WHERE key = 'swing_weight_setup' AND value = '0';
UPDATE algo_config SET value = '20' WHERE key = 'swing_weight_trend' AND value = '0';
UPDATE algo_config SET value = '20' WHERE key = 'swing_weight_momentum' AND value = '0';
UPDATE algo_config SET value = '12' WHERE key = 'swing_weight_volume' AND value = '0';
UPDATE algo_config SET value = '10' WHERE key = 'swing_weight_fundamentals' AND value = '0';
UPDATE algo_config SET value = '8'  WHERE key = 'swing_weight_sector' AND value = '0';
UPDATE algo_config SET value = '5'  WHERE key = 'swing_weight_multi_timeframe' AND value = '0';

-- Also ensure the keys exist with correct values if missing entirely
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('swing_weight_setup', '25', 'int', 'Swing score setup quality weight pct', 'migration-083')
ON CONFLICT (key) DO NOTHING;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('swing_weight_trend', '20', 'int', 'Swing score trend quality weight pct', 'migration-083')
ON CONFLICT (key) DO NOTHING;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('swing_weight_momentum', '20', 'int', 'Swing score momentum RS weight pct', 'migration-083')
ON CONFLICT (key) DO NOTHING;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('swing_weight_volume', '12', 'int', 'Swing score volume weight pct', 'migration-083')
ON CONFLICT (key) DO NOTHING;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('swing_weight_fundamentals', '10', 'int', 'Swing score fundamentals weight pct', 'migration-083')
ON CONFLICT (key) DO NOTHING;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('swing_weight_sector', '8', 'int', 'Swing score sector industry weight pct', 'migration-083')
ON CONFLICT (key) DO NOTHING;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('swing_weight_multi_timeframe', '5', 'int', 'Swing score multi-timeframe weight pct', 'migration-083')
ON CONFLICT (key) DO NOTHING;
