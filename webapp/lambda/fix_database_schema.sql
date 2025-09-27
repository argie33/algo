-- Fix database schema issues

-- Drop and recreate technical_data_daily with correct columns
DROP TABLE IF EXISTS technical_data_daily CASCADE;
CREATE TABLE IF NOT EXISTS technical_data_daily (
    symbol VARCHAR(50),
    date TIMESTAMP,
    rsi DOUBLE PRECISION,
    macd DOUBLE PRECISION,
    macd_signal DOUBLE PRECISION,
    macd_hist DOUBLE PRECISION,
    mom DOUBLE PRECISION,
    roc DOUBLE PRECISION,
    adx DOUBLE PRECISION,
    plus_di DOUBLE PRECISION,
    minus_di DOUBLE PRECISION,
    atr DOUBLE PRECISION,
    ad DOUBLE PRECISION,
    cmf DOUBLE PRECISION,
    mfi DOUBLE PRECISION,
    td_sequential INTEGER,
    td_combo INTEGER,
    marketwatch DOUBLE PRECISION,
    dm DOUBLE PRECISION,
    sma_10 DOUBLE PRECISION,
    sma_20 DOUBLE PRECISION,
    sma_50 DOUBLE PRECISION,
    sma_150 DOUBLE PRECISION,
    sma_200 DOUBLE PRECISION,
    ema_4 DOUBLE PRECISION,
    ema_9 DOUBLE PRECISION,
    ema_21 DOUBLE PRECISION,
    bbands_lower DOUBLE PRECISION,
    bbands_middle DOUBLE PRECISION,
    bbands_upper DOUBLE PRECISION,
    pivot_high DOUBLE PRECISION,
    pivot_low DOUBLE PRECISION,
    pivot_high_triggered BOOLEAN,
    pivot_low_triggered BOOLEAN,
    fetched_at TIMESTAMP
);

-- Add missing dividend_calendar company_name column properly
ALTER TABLE dividend_calendar ADD COLUMN IF NOT EXISTS company_name VARCHAR(255);

-- Ensure buy_sell_daily table exists
CREATE TABLE IF NOT EXISTS buy_sell_daily (
    symbol VARCHAR(50),
    timeframe VARCHAR(20),
    date TIMESTAMP,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume BIGINT,
    signal VARCHAR(10),
    buylevel DOUBLE PRECISION,
    stoplevel DOUBLE PRECISION,
    inposition BOOLEAN DEFAULT FALSE
);

-- Create buy_sell_weekly table for signals
CREATE TABLE IF NOT EXISTS buy_sell_weekly (
    symbol VARCHAR(50),
    timeframe VARCHAR(20),
    date TIMESTAMP,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume BIGINT,
    signal VARCHAR(10),
    buylevel DOUBLE PRECISION,
    stoplevel DOUBLE PRECISION,
    inposition BOOLEAN DEFAULT FALSE
);

-- Insert test data for technical_data_daily
INSERT INTO technical_data_daily (symbol, date, rsi, macd, macd_signal, macd_hist, mom, roc, adx, plus_di, minus_di, atr, ad, cmf, mfi, td_sequential, td_combo, marketwatch, dm, sma_10, sma_20, sma_50, sma_150, sma_200, ema_4, ema_9, ema_21, bbands_lower, bbands_middle, bbands_upper, pivot_high, pivot_low, pivot_high_triggered, pivot_low_triggered, fetched_at) VALUES
('AAPL', '2024-01-01', 65.4, 0.82, 0.75, 0.07, 2.1, 3.2, 45.2, 25.1, 18.7, 1.8, 125000, 0.15, 72.3, 9, 13, 0.5, 1.2, 180.25, 178.50, 175.80, 170.25, 165.90, 181.10, 179.85, 177.20, 174.50, 179.25, 184.00, 182.00, 176.50, false, false, '2024-01-01 09:30:00'),
('MSFT', '2024-01-01', 58.2, 1.45, 1.32, 0.13, 3.8, 4.5, 52.8, 28.4, 21.2, 2.1, 180000, 0.22, 68.9, 7, 11, 0.6, 1.5, 425.30, 422.80, 418.50, 410.25, 405.90, 426.10, 424.85, 421.20, 420.50, 425.25, 430.00, 428.00, 418.50, false, false, '2024-01-01 09:30:00'),
('GOOGL', '2024-01-01', 42.1, -0.25, -0.18, -0.07, -1.2, -2.1, 38.5, 22.8, 26.4, 1.5, 95000, -0.08, 45.6, 3, 5, 0.3, 0.8, 138.45, 136.20, 134.80, 132.25, 128.90, 139.10, 137.85, 135.20, 134.50, 137.25, 140.00, 140.50, 135.00, false, true, '2024-01-01 09:30:00'),
('TSLA', '2024-01-01', 72.8, 2.15, 1.85, 0.30, 8.2, 12.5, 48.9, 32.1, 19.8, 3.2, 210000, 0.35, 78.4, 11, 15, 0.8, 2.1, 255.75, 252.50, 248.80, 240.25, 235.90, 257.10, 254.85, 251.20, 248.50, 253.25, 258.00, 260.00, 246.50, false, false, '2024-01-01 09:30:00'),
('AMZN', '2024-01-01', 55.6, 0.95, 0.88, 0.07, 2.8, 4.1, 41.2, 24.6, 22.8, 1.9, 150000, 0.18, 62.3, 5, 8, 0.4, 1.1, 148.90, 146.80, 144.50, 140.25, 136.90, 149.60, 148.35, 146.70, 144.50, 147.25, 150.00, 151.00, 144.00, false, false, '2024-01-01 09:30:00')
ON CONFLICT DO NOTHING;

-- Insert test data for buy_sell_daily
INSERT INTO buy_sell_daily (symbol, timeframe, date, open, high, low, close, volume, signal, buylevel, stoplevel, inposition) VALUES
('AAPL', 'daily', '2024-01-01', 180.00, 182.50, 178.25, 180.25, 52000000, 'BUY', 178.50, 175.00, true),
('MSFT', 'daily', '2024-01-01', 425.00, 427.80, 422.50, 425.30, 35000000, 'HOLD', 420.00, 415.00, false),
('GOOGL', 'daily', '2024-01-01', 138.00, 140.50, 136.75, 138.45, 28000000, 'SELL', 135.00, 130.00, false),
('TSLA', 'daily', '2024-01-01', 255.00, 260.00, 252.00, 255.75, 45000000, 'BUY', 250.00, 245.00, true),
('AMZN', 'daily', '2024-01-01', 148.50, 151.00, 146.25, 148.90, 38000000, 'HOLD', 145.00, 140.00, false)
ON CONFLICT DO NOTHING;
