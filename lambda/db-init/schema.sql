-- MACD Schema Migration - Add missing columns to buy_sell tables

ALTER TABLE buy_sell_daily ADD COLUMN IF NOT EXISTS macd DECIMAL(10, 2);
ALTER TABLE buy_sell_daily ADD COLUMN IF NOT EXISTS macd_signal DECIMAL(10, 2);

ALTER TABLE buy_sell_weekly ADD COLUMN IF NOT EXISTS macd DECIMAL(10, 2);
ALTER TABLE buy_sell_weekly ADD COLUMN IF NOT EXISTS macd_signal DECIMAL(10, 2);

ALTER TABLE buy_sell_monthly ADD COLUMN IF NOT EXISTS macd DECIMAL(10, 2);
ALTER TABLE buy_sell_monthly ADD COLUMN IF NOT EXISTS macd_signal DECIMAL(10, 2);
