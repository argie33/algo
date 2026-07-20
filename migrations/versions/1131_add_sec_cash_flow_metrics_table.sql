-- Migration 1131: Create sec_cash_flow_metrics table.
--
-- ROOT CAUSE: loaders/load_sec_cash_flow_metrics.py (table_name = "sec_cash_flow_metrics")
-- has existed since Session 274 and is registered as a "critical" (cannot-tolerate-
-- interruption) production loader in terraform/modules/loaders/main.tf, but no migration
-- or schema.sql entry ever created its destination table. Every run (local or AWS) would
-- fail on INSERT with "relation sec_cash_flow_metrics does not exist" - confirmed live
-- against the local DB 2026-07-20 (table absent from information_schema.tables). The
-- loader's source data (annual_cash_flow, annual_balance_sheet, annual_income_statement)
-- is real and already populated; only the destination table was missing.
--
-- Columns match exactly what SecCashFlowMetricsLoader.fetch_incremental() writes
-- (loaders/load_sec_cash_flow_metrics.py), following the positioning_metrics /
-- stability_metrics precedent in lambda/db-init/schema.sql.

CREATE TABLE IF NOT EXISTS sec_cash_flow_metrics (
    symbol VARCHAR(20) NOT NULL PRIMARY KEY,
    working_capital NUMERIC(20, 2),
    capex NUMERIC(20, 2),
    free_cash_flow NUMERIC(20, 2),
    operating_cash_flow NUMERIC(20, 2),
    cash_conversion_rate NUMERIC(10, 4),
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),
    computed_at DATE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sec_cash_flow_metrics_updated_at ON sec_cash_flow_metrics(updated_at DESC);
