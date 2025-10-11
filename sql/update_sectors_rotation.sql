-- Add rotation columns to sectors table for sector rotation analysis
-- These columns are populated by loadsectordata.py from yfinance

ALTER TABLE sectors ADD COLUMN IF NOT EXISTS flow VARCHAR(20);
ALTER TABLE sectors ADD COLUMN IF NOT EXISTS performance NUMERIC(10,4);
ALTER TABLE sectors ALTER COLUMN momentum TYPE VARCHAR(20);

-- Create trigger to sync sectors table with sector_performance updates
CREATE OR REPLACE FUNCTION sync_sector_rotation()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO sectors (sector, stock_count, total_volume, momentum, flow, performance)
    VALUES (NEW.sector_name, 1, NEW.volume, NEW.momentum, NEW.money_flow, NEW.performance_1d)
    ON CONFLICT (sector) DO UPDATE SET
        momentum = EXCLUDED.momentum,
        flow = EXCLUDED.flow,
        performance = EXCLUDED.performance,
        total_volume = EXCLUDED.total_volume,
        timestamp = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop trigger if exists and recreate
DROP TRIGGER IF EXISTS sync_sector_rotation_trigger ON sector_performance;
CREATE TRIGGER sync_sector_rotation_trigger
AFTER INSERT OR UPDATE ON sector_performance
FOR EACH ROW
EXECUTE FUNCTION sync_sector_rotation();

-- Initial population from existing sector_performance data
INSERT INTO sectors (sector, stock_count, total_volume, momentum, flow, performance)
SELECT
    sector_name,
    1,
    volume,
    momentum,
    money_flow,
    performance_1d
FROM sector_performance
ON CONFLICT (sector) DO UPDATE SET
    momentum = EXCLUDED.momentum,
    flow = EXCLUDED.flow,
    performance = EXCLUDED.performance,
    total_volume = EXCLUDED.total_volume,
    timestamp = CURRENT_TIMESTAMP;
