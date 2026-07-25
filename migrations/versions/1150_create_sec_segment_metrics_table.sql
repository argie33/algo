-- Migration 1150: Create sec_segment_metrics table
--
-- Purpose: Table missing but referenced by load_sec_segment_metrics.py loader
-- Stores business segment analysis for diversification scoring
-- Data extracted from SEC 10-K/10-Q FASB ASC 280 segment disclosures

CREATE TABLE IF NOT EXISTS sec_segment_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    segment_count INTEGER,
    largest_segment_revenue_pct NUMERIC(5, 2),
    revenue_concentration_hhi NUMERIC(5, 3),
    is_diversified BOOLEAN,
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR,
    reason_type VARCHAR,
    computed_at DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol)
);

CREATE INDEX idx_sec_segment_metrics_symbol ON sec_segment_metrics(symbol);
CREATE INDEX idx_sec_segment_metrics_computed_at ON sec_segment_metrics(computed_at);

-- Add to data_loader_status tracking
INSERT INTO data_loader_status (table_name, completion_pct, last_updated)
VALUES ('sec_segment_metrics', 0.0, NOW())
ON CONFLICT (table_name) DO UPDATE
SET last_updated = NOW();
