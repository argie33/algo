-- Portfolio Test Data
-- Insert sample portfolio holdings and performance data for testing
-- Run with: psql -h localhost -U postgres -d stocks -f portfolio-test-data.sql

-- Test user ID
-- Note: Using 'test-user' for local testing (ensure this matches your auth setup)

-- Clear existing portfolio test data
DELETE FROM portfolio_holdings WHERE user_id = 'test-user';
DELETE FROM portfolio_performance WHERE user_id = 'test-user';

-- Insert sample portfolio holdings with real stock data
-- Portfolio: $50,000 invested in 5 tech stocks
INSERT INTO portfolio_holdings (
  user_id, symbol, quantity, average_cost, current_price,
  market_value, unrealized_pnl, unrealized_pnl_percent,
  last_updated, updated_at
) VALUES
  -- AAPL: 40 shares @ $200 avg = $8,000 cost, now $225.50 = $9,020
  ('test-user', 'AAPL', 40.0000, 200.0000, 225.50, 9020.00, 1020.00, 12.75, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),

  -- MSFT: 15 shares @ $380 avg = $5,700 cost, now $425.30 = $6,379.50
  ('test-user', 'MSFT', 15.0000, 380.0000, 425.30, 6379.50, 679.50, 11.92, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),

  -- GOOGL: 25 shares @ $130 avg = $3,250 cost, now $165.80 = $4,145
  ('test-user', 'GOOGL', 25.0000, 130.0000, 165.80, 4145.00, 895.00, 27.54, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),

  -- TSLA: 30 shares @ $220 avg = $6,600 cost, now $265.75 = $7,972.50
  ('test-user', 'TSLA', 30.0000, 220.0000, 265.75, 7972.50, 1372.50, 20.80, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),

  -- AMZN: 50 shares @ $175 avg = $8,750 cost, now $188.45 = $9,422.50
  ('test-user', 'AMZN', 50.0000, 175.0000, 188.45, 9422.50, 1422.50, 16.26, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- Insert portfolio performance history (last 90 days of daily data)
-- Starting portfolio value: $32,300, Current: $36,939.50
-- Cumulative gain: 14.33%

INSERT INTO portfolio_performance (
  user_id, date, total_value, total_cost, cash_balance,
  day_change, day_change_percent, total_return, total_return_percent,
  daily_pnl_percent, broker, created_at
) VALUES
  -- Starting point (90 days ago)
  ('test-user', '2025-07-10', 32300.00, 32300.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 'combined', '2025-07-10 09:30:00'),

  -- Day 1 (+0.5%)
  ('test-user', '2025-07-11', 32461.50, 32300.00, 0.00, 161.50, 0.50, 161.50, 0.50, 0.50, 'combined', '2025-07-11 16:00:00'),

  -- Day 2 (-0.3%)
  ('test-user', '2025-07-14', 32373.30, 32300.00, 0.00, -88.20, -0.27, 73.30, 0.23, -0.27, 'combined', '2025-07-14 16:00:00'),

  -- Day 3 (+1.2%)
  ('test-user', '2025-07-15', 32788.30, 32300.00, 0.00, 415.00, 1.28, 488.30, 1.51, 1.28, 'combined', '2025-07-15 16:00:00'),

  -- Day 4 (+0.8%)
  ('test-user', '2025-07-16', 33050.00, 32300.00, 0.00, 261.70, 0.80, 750.00, 2.32, 0.80, 'combined', '2025-07-16 16:00:00'),

  -- Day 5 (-1.5%)
  ('test-user', '2025-07-17', 32555.75, 32300.00, 0.00, -494.25, -1.49, 255.75, 0.79, -1.49, 'combined', '2025-07-17 16:00:00'),

  -- Week 2 mixed performance
  ('test-user', '2025-07-18', 32892.50, 32300.00, 0.00, 336.75, 1.03, 592.50, 1.83, 1.03, 'combined', '2025-07-18 16:00:00'),
  ('test-user', '2025-07-21', 32756.80, 32300.00, 0.00, -135.70, -0.41, 456.80, 1.41, -0.41, 'combined', '2025-07-21 16:00:00'),
  ('test-user', '2025-07-22', 33215.40, 32300.00, 0.00, 458.60, 1.40, 915.40, 2.83, 1.40, 'combined', '2025-07-22 16:00:00'),
  ('test-user', '2025-07-23', 33450.00, 32300.00, 0.00, 234.60, 0.71, 1150.00, 3.56, 0.71, 'combined', '2025-07-23 16:00:00'),
  ('test-user', '2025-07-24', 33100.50, 32300.00, 0.00, -349.50, -1.04, 800.50, 2.48, -1.04, 'combined', '2025-07-24 16:00:00'),

  -- Week 3-4: Positive trend
  ('test-user', '2025-07-25', 33520.00, 32300.00, 0.00, 419.50, 1.27, 1220.00, 3.77, 1.27, 'combined', '2025-07-25 16:00:00'),
  ('test-user', '2025-07-28', 33800.00, 32300.00, 0.00, 280.00, 0.84, 1500.00, 4.64, 0.84, 'combined', '2025-07-28 16:00:00'),
  ('test-user', '2025-07-29', 34150.00, 32300.00, 0.00, 350.00, 1.03, 1850.00, 5.72, 1.03, 'combined', '2025-07-29 16:00:00'),
  ('test-user', '2025-07-30', 33950.00, 32300.00, 0.00, -200.00, -0.59, 1650.00, 5.11, -0.59, 'combined', '2025-07-30 16:00:00'),
  ('test-user', '2025-07-31', 34300.00, 32300.00, 0.00, 350.00, 1.03, 2000.00, 6.19, 1.03, 'combined', '2025-07-31 16:00:00'),

  -- August: Volatility
  ('test-user', '2025-08-01', 34150.00, 32300.00, 0.00, -150.00, -0.44, 1850.00, 5.72, -0.44, 'combined', '2025-08-01 16:00:00'),
  ('test-user', '2025-08-04', 33800.00, 32300.00, 0.00, -350.00, -1.02, 1500.00, 4.64, -1.02, 'combined', '2025-08-04 16:00:00'),
  ('test-user', '2025-08-05', 34500.00, 32300.00, 0.00, 700.00, 2.07, 2200.00, 6.81, 2.07, 'combined', '2025-08-05 16:00:00'),
  ('test-user', '2025-08-06', 34200.00, 32300.00, 0.00, -300.00, -0.87, 1900.00, 5.88, -0.87, 'combined', '2025-08-06 16:00:00'),
  ('test-user', '2025-08-07', 34750.00, 32300.00, 0.00, 550.00, 1.61, 2450.00, 7.58, 1.61, 'combined', '2025-08-07 16:00:00'),
  ('test-user', '2025-08-08', 35100.00, 32300.00, 0.00, 350.00, 1.01, 2800.00, 8.67, 1.01, 'combined', '2025-08-08 16:00:00'),
  ('test-user', '2025-08-11', 35350.00, 32300.00, 0.00, 250.00, 0.71, 3050.00, 9.44, 0.71, 'combined', '2025-08-11 16:00:00'),
  ('test-user', '2025-08-12', 35750.00, 32300.00, 0.00, 400.00, 1.13, 3450.00, 10.68, 1.13, 'combined', '2025-08-12 16:00:00'),
  ('test-user', '2025-08-13', 35500.00, 32300.00, 0.00, -250.00, -0.70, 3200.00, 9.91, -0.70, 'combined', '2025-08-13 16:00:00'),
  ('test-user', '2025-08-14', 35900.00, 32300.00, 0.00, 400.00, 1.13, 3600.00, 11.14, 1.13, 'combined', '2025-08-14 16:00:00'),
  ('test-user', '2025-08-15', 36100.00, 32300.00, 0.00, 200.00, 0.56, 3800.00, 11.77, 0.56, 'combined', '2025-08-15 16:00:00'),

  -- Recent: Strong performance last 5 days
  ('test-user', '2025-08-18', 36300.00, 32300.00, 0.00, 200.00, 0.55, 4000.00, 12.38, 0.55, 'combined', '2025-08-18 16:00:00'),
  ('test-user', '2025-08-19', 36550.00, 32300.00, 0.00, 250.00, 0.69, 4250.00, 13.15, 0.69, 'combined', '2025-08-19 16:00:00'),
  ('test-user', '2025-08-20', 36750.00, 32300.00, 0.00, 200.00, 0.55, 4450.00, 13.77, 0.55, 'combined', '2025-08-20 16:00:00'),
  ('test-user', '2025-08-21', 36850.00, 32300.00, 0.00, 100.00, 0.27, 4550.00, 14.08, 0.27, 'combined', '2025-08-21 16:00:00'),
  ('test-user', '2025-08-22', 36939.50, 32300.00, 0.00, 89.50, 0.24, 4639.50, 14.35, 0.24, 'combined', '2025-08-22 16:00:00');

-- Verify data was inserted
SELECT 'portfolio_holdings' as table_name, COUNT(*) as row_count FROM portfolio_holdings WHERE user_id = 'test-user'
UNION ALL
SELECT 'portfolio_performance', COUNT(*) FROM portfolio_performance WHERE user_id = 'test-user';
