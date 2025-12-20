-- Seed T10Y2Y (10Y-2Y yield spread), SP500, HOUST, and MICH data for local testing
-- This provides economic indicators needed for EconomicModeling page

-- Delete any existing data for these series
DELETE FROM economic_data WHERE series_id IN ('T10Y2Y', 'SP500', 'HOUST', 'MICH');

-- Insert T10Y2Y (10-Year minus 2-Year Treasury yield spread) data
-- Recent values showing yield curve dynamics
INSERT INTO economic_data (series_id, date, value) VALUES
-- October 2025 - Slight positive spread (normal curve)
('T10Y2Y', '2025-10-03', 0.45),
('T10Y2Y', '2025-10-02', 0.42),
('T10Y2Y', '2025-10-01', 0.38),
-- September 2025 - Narrowing spread
('T10Y2Y', '2025-09-30', 0.35),
('T10Y2Y', '2025-09-29', 0.32),
('T10Y2Y', '2025-09-28', 0.28),
('T10Y2Y', '2025-09-27', 0.25),
('T10Y2Y', '2025-09-26', 0.22),
-- Earlier September - Near zero (flattening)
('T10Y2Y', '2025-09-20', 0.15),
('T10Y2Y', '2025-09-15', 0.08),
('T10Y2Y', '2025-09-10', 0.05),
('T10Y2Y', '2025-09-05', 0.02),
-- August 2025 - Inverted curve (recession signal)
('T10Y2Y', '2025-08-30', -0.05),
('T10Y2Y', '2025-08-25', -0.12),
('T10Y2Y', '2025-08-20', -0.18),
('T10Y2Y', '2025-08-15', -0.22),
('T10Y2Y', '2025-08-10', -0.28),
('T10Y2Y', '2025-08-05', -0.32),
-- July 2025 - Deepening inversion
('T10Y2Y', '2025-07-30', -0.35),
('T10Y2Y', '2025-07-25', -0.38),
('T10Y2Y', '2025-07-20', -0.42),
('T10Y2Y', '2025-07-15', -0.45),
('T10Y2Y', '2025-07-10', -0.48),
('T10Y2Y', '2025-07-05', -0.52),
-- June 2025 - Peak inversion
('T10Y2Y', '2025-06-30', -0.55),
('T10Y2Y', '2025-06-25', -0.58),
('T10Y2Y', '2025-06-20', -0.62),
('T10Y2Y', '2025-06-15', -0.65),
-- Historical data for trend analysis
('T10Y2Y', '2025-05-30', -0.48),
('T10Y2Y', '2025-04-30', -0.35),
('T10Y2Y', '2025-03-30', -0.22),
('T10Y2Y', '2025-02-28', -0.15),
('T10Y2Y', '2025-01-31', -0.08),
('T10Y2Y', '2024-12-31', 0.05),
('T10Y2Y', '2024-11-30', 0.18),
('T10Y2Y', '2024-10-31', 0.32),
('T10Y2Y', '2024-09-30', 0.45);

-- Insert SP500 data (S&P 500 index values)
INSERT INTO economic_data (series_id, date, value) VALUES
-- October 2025 - Current levels
('SP500', '2025-10-03', 5825.50),
('SP500', '2025-10-02', 5812.30),
('SP500', '2025-10-01', 5798.75),
-- September 2025 - Steady gains
('SP500', '2025-09-30', 5785.20),
('SP500', '2025-09-29', 5771.45),
('SP500', '2025-09-28', 5758.90),
('SP500', '2025-09-27', 5745.60),
('SP500', '2025-09-26', 5732.15),
('SP500', '2025-09-20', 5698.25),
('SP500', '2025-09-15', 5665.80),
('SP500', '2025-09-10', 5632.45),
('SP500', '2025-09-05', 5598.90),
-- August 2025 - Volatility
('SP500', '2025-08-30', 5565.25),
('SP500', '2025-08-25', 5532.70),
('SP500', '2025-08-20', 5498.15),
('SP500', '2025-08-15', 5465.80),
('SP500', '2025-08-10', 5432.45),
('SP500', '2025-08-05', 5398.90),
-- July 2025 - Recovery
('SP500', '2025-07-30', 5365.25),
('SP500', '2025-07-25', 5332.70),
('SP500', '2025-07-20', 5298.15),
('SP500', '2025-07-15', 5265.80),
('SP500', '2025-07-10', 5232.45),
('SP500', '2025-07-05', 5198.90),
-- June 2025 - Correction
('SP500', '2025-06-30', 5165.25),
('SP500', '2025-06-25', 5132.70),
('SP500', '2025-06-20', 5098.15),
('SP500', '2025-06-15', 5065.80),
-- Historical monthly data
('SP500', '2025-05-30', 5232.45),
('SP500', '2025-04-30', 5398.90),
('SP500', '2025-03-30', 5565.25),
('SP500', '2025-02-28', 5698.25),
('SP500', '2025-01-31', 5832.15),
('SP500', '2024-12-31', 5965.80),
('SP500', '2024-11-30', 6098.45),
('SP500', '2024-10-31', 6232.70),
('SP500', '2024-09-30', 6365.25);

-- Insert HOUST (Housing Starts) data - thousands of units
INSERT INTO economic_data (series_id, date, value) VALUES
-- October 2025
('HOUST', '2025-10-03', 1420),
('HOUST', '2025-09-30', 1415),
-- Recent months
('HOUST', '2025-09-01', 1398),
('HOUST', '2025-08-01', 1385),
('HOUST', '2025-07-01', 1372),
('HOUST', '2025-06-01', 1361),
('HOUST', '2025-05-01', 1348),
('HOUST', '2025-04-01', 1335),
('HOUST', '2025-03-01', 1322),
('HOUST', '2025-02-01', 1310),
('HOUST', '2025-01-01', 1298),
('HOUST', '2024-12-01', 1285),
('HOUST', '2024-11-01', 1272),
('HOUST', '2024-10-01', 1260);

-- Insert MICH (Michigan Consumer Sentiment Index) data
INSERT INTO economic_data (series_id, date, value) VALUES
-- October 2025
('MICH', '2025-10-03', 68.5),
('MICH', '2025-09-30', 67.2),
-- Recent months
('MICH', '2025-09-01', 66.8),
('MICH', '2025-08-01', 65.4),
('MICH', '2025-07-01', 64.1),
('MICH', '2025-06-01', 62.7),
('MICH', '2025-05-01', 61.3),
('MICH', '2025-04-01', 59.9),
('MICH', '2025-03-01', 58.6),
('MICH', '2025-02-01', 57.2),
('MICH', '2025-01-01', 55.8),
('MICH', '2024-12-01', 54.5),
('MICH', '2024-11-01', 53.1),
('MICH', '2024-10-01', 51.8);

-- Verify the inserts
SELECT
    series_id,
    COUNT(*) as count,
    MIN(date) as earliest,
    MAX(date) as latest,
    ROUND(AVG(value)::numeric, 2) as avg_value,
    ROUND(MIN(value)::numeric, 2) as min_value,
    ROUND(MAX(value)::numeric, 2) as max_value
FROM economic_data
WHERE series_id IN ('T10Y2Y', 'SP500', 'HOUST', 'MICH')
GROUP BY series_id
ORDER BY series_id;
