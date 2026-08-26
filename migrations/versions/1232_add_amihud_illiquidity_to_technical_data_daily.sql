-- Migration 1232: Add amihud_illiquidity to technical_data_daily
--
-- Closes the gap documented in liquidity_amihud_gap_flagged_not_implemented_20260825: Amihud
-- (2002, Journal of Financial Markets) illiquidity - |monthly return| / average daily dollar
-- volume - was found to be a real, distinct signal (t=3.34 vs forward 1-month return, 126
-- months 2016-2026; correlation with log(market_cap) only -0.18, not a Size duplicate) but was
-- not implemented because no existing table stored the underlying daily |return|/dollar-volume
-- computation. technical_data_daily's own volume_ma_20 was checked as a possible base and found
-- 100% NULL (dead column, computed nowhere) - confirmed again here rather than trusted from the
-- prior note. volume_ma_50 is NOT dead (95.9% populated, computed by
-- loaders/load_technical_indicators.py's compute_volume_ma) but is a simple volume average, not
-- an illiquidity ratio, so it can't stand in for this.
--
-- Computed by loaders/load_technical_indicators.py as a trailing 21-trading-day rolling mean of
-- daily |return| / dollar_volume, scaled by 1e6 for a readable NUMERIC magnitude (raw ratio is
-- ~1e-8 to 1e-6 for a liquid large-cap symbol).

ALTER TABLE technical_data_daily
    ADD COLUMN IF NOT EXISTS amihud_illiquidity NUMERIC;
