-- Migration 1296: Add patrol_corporate_action_rise_ratio config key
-- The corporate-action price-sanity check was drop-only (blind to reverse splits); the
-- symmetric rise-side threshold was added to data_patrol_config.py/config_schema.py but
-- never seeded into algo_config. DataPatrol logs CONFIG CRITICAL and falls back to the
-- 0.30 default without this row.

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
  ('patrol_corporate_action_rise_ratio', '0.30', 'float',
   'Price rise ratio threshold that triggers corporate action alert (reverse splits) in data patrol', 'migration-1296')
ON CONFLICT (key) DO NOTHING;
