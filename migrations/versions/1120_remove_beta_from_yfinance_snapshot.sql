-- Session 196: Remove redundant beta from yfinance_snapshot
-- Beta is already computed from price_daily in load_risk_metrics_daily.py
-- and stored in stability_metrics table. yfinance beta fetch is unused.
-- Removing saves ~4% of yfinance API calls with no data quality loss.

ALTER TABLE yfinance_snapshot DROP COLUMN beta;
