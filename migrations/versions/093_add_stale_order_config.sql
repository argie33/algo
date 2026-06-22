-- Migration 093: Add missing stale order config keys
-- stale_order_alert_minutes and stale_order_auto_cancel_minutes are required by
-- position_monitor.check_stale_orders() but were never seeded in algo_config.

INSERT INTO algo_config (key, value, description, updated_by)
VALUES
    ('stale_order_alert_minutes',       '30',   'Alert when open orders are older than this many minutes', 'migration-093'),
    ('stale_order_auto_cancel_minutes', '120',  'Auto-cancel open orders older than this many minutes (0 = disabled)', 'migration-093')
ON CONFLICT (key) DO NOTHING;
