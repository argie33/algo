-- Migration 079: Create economic_metrics_daily table
-- Table exists in schema.sql but was never added as a versioned migration,
-- so existing databases are missing it. The economic_metrics_daily loader
-- fails with "Table economic_metrics_daily does not exist" until this runs.

CREATE TABLE IF NOT EXISTS economic_metrics_daily (
    report_date DATE PRIMARY KEY,
    cpi_yoy_pct NUMERIC(8, 2),
    cpi_yoy_error TEXT,
    spy_price_change_pct NUMERIC(8, 2),
    spy_price_change_error TEXT,
    yield_curve_slope_10y2y NUMERIC(8, 3),
    yield_curve_slope_error TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_economic_metrics_daily_date ON economic_metrics_daily(report_date DESC);
