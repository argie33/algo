-- Migration 106: Add missing patrol_corporate_action config keys
-- DataPatrol fails at startup with CONFIG CRITICAL if these are absent.
-- Values match the docstring defaults in data_patrol_config.get_corporate_actions_config().

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
  ('patrol_corporate_action_lookback_days', '90', 'int',
   'Days of lookback for detecting corporate actions (splits/dividends) in data patrol', 'migration-106'),
  ('patrol_corporate_action_drop_ratio', '-0.30', 'float',
   'Price drop ratio threshold that triggers corporate action alert in data patrol', 'migration-106')
ON CONFLICT (key) DO NOTHING;
