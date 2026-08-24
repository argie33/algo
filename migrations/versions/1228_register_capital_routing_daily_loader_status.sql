-- Migration 1228: Register capital_routing_daily in data_loader_status
--
-- 1227_create_capital_routing_daily.sql created the table but, unlike every other new-table
-- migration in this codebase (see e.g. 1157_create_sec_segment_info_table.sql), never
-- registered it in data_loader_status. Consequence: the table inventory endpoint
-- (lambda/api/routes/algo_handlers/inventory.py's _get_table_inventory, backing the
-- dashboard's "inventory" panel) classifies any table not in data_loader_status as
-- "untracked" - capital_routing_daily was showing up there even though
-- loaders/load_market_status_daily.py has been populating it correctly since 4bc36eca9,
-- a false "this table fell through the cracks" signal for an operator reviewing that panel.

INSERT INTO data_loader_status (table_name, completion_pct, last_updated)
VALUES ('capital_routing_daily', 0.0, NOW())
ON CONFLICT (table_name) DO UPDATE
SET last_updated = NOW();
