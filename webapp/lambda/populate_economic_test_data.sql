-- Populate economic data for tests
-- Create economic_data table if it doesn't exist (matches loadecondata.py schema)
CREATE TABLE IF NOT EXISTS economic_data (
    series_id TEXT NOT NULL,
    date DATE NOT NULL,
    value DOUBLE PRECISION,
    PRIMARY KEY (series_id, date)
);

-- Clear existing test data
DELETE FROM economic_data WHERE series_id IN ('GDP', 'CPI', 'UNRATE', 'VIXCLS', 'FEDFUNDS', 'CPIAUCSL', 'GDPC1');

-- Insert sample economic data that tests expect
INSERT INTO economic_data (series_id, date, value) VALUES
-- GDP data
('GDP', '2025-01-01', 27000000),
('GDP', '2024-10-01', 26800000),
('GDP', '2024-07-01', 26600000),
('GDP', '2024-04-01', 26400000),
('GDP', '2024-01-01', 26200000),

-- GDPC1 (Real GDP)
('GDPC1', '2025-01-01', 22500000),
('GDPC1', '2024-10-01', 22400000),
('GDPC1', '2024-07-01', 22300000),
('GDPC1', '2024-04-01', 22200000),
('GDPC1', '2024-01-01', 22100000),

-- CPI data
('CPI', '2025-01-01', 307.789),
('CPI', '2024-12-01', 307.026),
('CPI', '2024-11-01', 306.746),
('CPI', '2024-10-01', 306.269),
('CPI', '2024-09-01', 305.691),

-- CPIAUCSL (Consumer Price Index for All Urban Consumers)
('CPIAUCSL', '2025-01-01', 307.789),
('CPIAUCSL', '2024-12-01', 307.026),
('CPIAUCSL', '2024-11-01', 306.746),
('CPIAUCSL', '2024-10-01', 306.269),
('CPIAUCSL', '2024-09-01', 305.691),

-- Unemployment Rate
('UNRATE', '2025-01-01', 3.7),
('UNRATE', '2024-12-01', 3.8),
('UNRATE', '2024-11-01', 3.9),
('UNRATE', '2024-10-01', 4.0),
('UNRATE', '2024-09-01', 4.1),

-- VIX Volatility Index
('VIXCLS', '2025-01-01', 15.39),
('VIXCLS', '2024-12-31', 16.45),
('VIXCLS', '2024-12-30', 15.82),
('VIXCLS', '2024-12-29', 14.98),
('VIXCLS', '2024-12-28', 15.67),

-- Federal Funds Rate
('FEDFUNDS', '2025-01-01', 5.25),
('FEDFUNDS', '2024-12-01', 5.25),
('FEDFUNDS', '2024-11-01', 5.00),
('FEDFUNDS', '2024-10-01', 5.00),
('FEDFUNDS', '2024-09-01', 4.75);

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_economic_data_series_date ON economic_data(series_id, date);

-- Verify data insertion
SELECT COUNT(*) as total_records, COUNT(DISTINCT series_id) as unique_series FROM economic_data;