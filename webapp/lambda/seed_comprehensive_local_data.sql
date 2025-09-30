-- Comprehensive Test Data for Local Development
-- Emulates data that AWS loaders (loadstockprices, loadstockscores, loadecondata, etc.) would provide
-- This script creates realistic dummy data for local development and testing

-- Clean existing data
DELETE FROM stock_scores;
DELETE FROM technical_data_daily;
DELETE FROM earnings;
DELETE FROM stock_prices;
DELETE FROM economic_data;

-- =============================================
-- SECTION 1: STOCK PRICES (90 days of historical data)
-- Emulates: loadstockprices.py loader
-- =============================================

-- Helper function to generate realistic price data with trends
DO $$
DECLARE
    symbols TEXT[] := ARRAY['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'META', 'AMZN', 'NFLX', 'AMD', 'CRM',
                            'JPM', 'BAC', 'KO', 'PG', 'JNJ', 'SPY', 'QQQ', 'VTI', 'IWM', 'GLD'];
    base_prices DECIMAL[] := ARRAY[178.50, 338.25, 138.75, 248.42, 465.30, 298.75, 145.86, 485.25, 165.40, 245.80,
                                   148.25, 35.42, 61.85, 145.30, 158.45, 450.25, 385.60, 215.30, 185.40, 185.25];
    sym TEXT;
    base_price DECIMAL;
    current_price DECIMAL;
    dt DATE;
    daily_change DECIMAL;
    open_price DECIMAL;
    high_price DECIMAL;
    low_price DECIMAL;
    close_price DECIMAL;
    daily_volume BIGINT;
    i INTEGER;
BEGIN
    FOR i IN 1..array_length(symbols, 1) LOOP
        sym := symbols[i];
        base_price := base_prices[i];
        current_price := base_price;

        -- Generate 90 days of historical price data
        FOR dt IN SELECT generate_series(CURRENT_DATE - INTERVAL '90 days', CURRENT_DATE - INTERVAL '1 day', '1 day'::interval)::date LOOP
            -- Skip weekends (simplified - doesn't handle holidays)
            IF EXTRACT(DOW FROM dt) NOT IN (0, 6) THEN
                -- Random daily change between -2% and +2%
                daily_change := (random() - 0.5) * 0.04;
                current_price := current_price * (1 + daily_change);

                -- Calculate OHLC prices
                open_price := current_price * (1 + (random() - 0.5) * 0.01);
                high_price := current_price * (1 + random() * 0.015);
                low_price := current_price * (1 - random() * 0.015);
                close_price := current_price;

                -- Volume varies by symbol (larger caps have more volume)
                IF i <= 7 THEN  -- Large cap tech
                    daily_volume := (50000000 + random() * 50000000)::BIGINT;
                ELSIF i <= 15 THEN  -- Mid cap / financials
                    daily_volume := (10000000 + random() * 20000000)::BIGINT;
                ELSE  -- ETFs
                    daily_volume := (30000000 + random() * 40000000)::BIGINT;
                END IF;

                INSERT INTO stock_prices (symbol, date, open, high, low, close, volume, adjusted_close)
                VALUES (sym, dt, open_price, high_price, low_price, close_price, daily_volume, close_price);
            END IF;
        END LOOP;

        RAISE NOTICE 'Generated price data for %', sym;
    END LOOP;
END $$;

-- =============================================
-- SECTION 2: TECHNICAL INDICATORS (daily)
-- Emulates: Technical analysis calculations
-- =============================================

DO $$
DECLARE
    symbols TEXT[] := ARRAY['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'META', 'AMZN', 'NFLX', 'AMD', 'CRM',
                            'JPM', 'BAC', 'KO', 'PG', 'JNJ', 'SPY', 'QQQ', 'VTI', 'IWM', 'GLD'];
    sym TEXT;
    dt DATE;
    latest_price DECIMAL;
    rsi_val DECIMAL;
    macd_val DECIMAL;
    sma_20_val DECIMAL;
    sma_50_val DECIMAL;
    sma_200_val DECIMAL;
    atr_val DECIMAL;
    volume_val BIGINT;
BEGIN
    FOR sym IN SELECT unnest(symbols) LOOP
        -- Generate technical data for last 90 days
        FOR dt IN SELECT generate_series(CURRENT_DATE - INTERVAL '90 days', CURRENT_DATE - INTERVAL '1 day', '1 day'::interval)::date LOOP
            -- Skip weekends
            IF EXTRACT(DOW FROM dt) NOT IN (0, 6) THEN
                -- Get actual price from stock_prices
                SELECT close, volume INTO latest_price, volume_val
                FROM stock_prices
                WHERE symbol = sym AND date = dt;

                IF latest_price IS NOT NULL THEN
                    -- Calculate SMA values (simplified - using current price with small offset)
                    sma_20_val := latest_price * (0.98 + random() * 0.04);
                    sma_50_val := latest_price * (0.96 + random() * 0.06);
                    sma_200_val := latest_price * (0.94 + random() * 0.08);

                    -- RSI typically ranges 30-70, occasionally hits extremes
                    rsi_val := 30 + random() * 40 + (CASE WHEN random() > 0.9 THEN random() * 20 ELSE 0 END);

                    -- MACD ranges from -5 to +5 for most stocks
                    macd_val := (random() - 0.5) * 10;

                    -- ATR (Average True Range) as percentage of price
                    atr_val := latest_price * (0.01 + random() * 0.02);

                    INSERT INTO technical_data_daily (symbol, date, rsi, macd, sma_20, sma_50, sma_200, atr)
                    VALUES (sym, dt, rsi_val, macd_val, sma_20_val, sma_50_val, sma_200_val, atr_val)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        rsi = EXCLUDED.rsi,
                        macd = EXCLUDED.macd,
                        sma_20 = EXCLUDED.sma_20,
                        sma_50 = EXCLUDED.sma_50,
                        sma_200 = EXCLUDED.sma_200,
                        atr = EXCLUDED.atr;
                END IF;
            END IF;
        END LOOP;

        RAISE NOTICE 'Generated technical data for %', sym;
    END LOOP;
END $$;

-- =============================================
-- SECTION 3: EARNINGS DATA (quarterly)
-- Emulates: Earnings data from financial APIs
-- =============================================

INSERT INTO earnings (symbol, report_date, actual_eps, estimated_eps) VALUES
-- AAPL - 8 quarters of data
('AAPL', '2024-11-01', 1.64, 1.60),
('AAPL', '2024-08-01', 1.40, 1.35),
('AAPL', '2024-05-02', 1.53, 1.50),
('AAPL', '2024-02-01', 2.18, 2.10),
('AAPL', '2023-11-02', 1.46, 1.39),
('AAPL', '2023-08-03', 1.26, 1.19),
('AAPL', '2023-05-04', 1.52, 1.43),
('AAPL', '2023-02-02', 1.88, 1.94),

-- MSFT
('MSFT', '2024-10-24', 3.30, 3.10),
('MSFT', '2024-07-25', 2.95, 2.93),
('MSFT', '2024-04-25', 2.94, 2.83),
('MSFT', '2024-01-25', 2.93, 2.78),
('MSFT', '2023-10-24', 2.99, 2.65),
('MSFT', '2023-07-25', 2.69, 2.55),
('MSFT', '2023-04-25', 2.45, 2.23),
('MSFT', '2023-01-24', 2.32, 2.29),

-- GOOGL
('GOOGL', '2024-10-29', 1.89, 1.85),
('GOOGL', '2024-07-23', 1.89, 1.84),
('GOOGL', '2024-04-25', 1.89, 1.51),
('GOOGL', '2024-01-30', 1.64, 1.59),
('GOOGL', '2023-10-24', 1.55, 1.45),
('GOOGL', '2023-07-25', 1.44, 1.34),
('GOOGL', '2023-04-25', 1.17, 1.07),
('GOOGL', '2023-02-02', 1.05, 1.18),

-- TSLA
('TSLA', '2024-10-23', 0.72, 0.58),
('TSLA', '2024-07-23', 0.52, 0.60),
('TSLA', '2024-04-23', 0.45, 0.51),
('TSLA', '2024-01-24', 0.71, 0.73),
('TSLA', '2023-10-18', 0.66, 0.73),
('TSLA', '2023-07-19', 0.91, 0.81),
('TSLA', '2023-04-19', 0.85, 0.85),
('TSLA', '2023-01-25', 1.19, 1.13),

-- NVDA
('NVDA', '2024-11-20', 0.81, 0.75),
('NVDA', '2024-08-28', 0.68, 0.64),
('NVDA', '2024-05-22', 0.60, 0.57),
('NVDA', '2024-02-21', 5.16, 4.59),
('NVDA', '2023-11-21', 4.02, 3.37),
('NVDA', '2023-08-23', 2.70, 2.07),
('NVDA', '2023-05-24', 1.09, 0.92),
('NVDA', '2023-02-22', 0.88, 0.81);

-- =============================================
-- SECTION 4: STOCK SCORES (calculated)
-- Emulates: loadstockscores.py loader output
-- =============================================

INSERT INTO stock_scores (symbol, composite_score, momentum_score, trend_score, value_score, quality_score, growth_score,
                         rsi, macd, sma_20, sma_50, volume_avg_30d, current_price, price_change_1d, price_change_5d,
                         price_change_30d, volatility_30d, market_cap, pe_ratio, score_date, last_updated)
SELECT
    sp.symbol,
    -- Composite score (weighted average)
    (55 + random() * 30)::DECIMAL(5,2) as composite_score,
    -- Momentum score based on RSI
    (50 + (td.rsi - 50) * 0.8)::DECIMAL(5,2) as momentum_score,
    -- Trend score based on price vs SMAs
    (50 + ((sp.close / td.sma_50 - 1) * 200))::DECIMAL(5,2) as trend_score,
    -- Value score (simplified - based on random for test data)
    (50 + random() * 30)::DECIMAL(5,2) as value_score,
    -- Quality score based on volatility
    (75 - td.atr / sp.close * 1000)::DECIMAL(5,2) as quality_score,
    -- Growth score based on earnings
    (60 + random() * 30)::DECIMAL(5,2) as growth_score,
    td.rsi,
    td.macd,
    td.sma_20,
    td.sma_50,
    AVG(sp.volume) OVER (PARTITION BY sp.symbol ORDER BY sp.date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)::BIGINT as volume_avg_30d,
    sp.close as current_price,
    ((sp.close - LAG(sp.close, 1) OVER (PARTITION BY sp.symbol ORDER BY sp.date)) / LAG(sp.close, 1) OVER (PARTITION BY sp.symbol ORDER BY sp.date) * 100)::DECIMAL(5,2) as price_change_1d,
    ((sp.close - LAG(sp.close, 5) OVER (PARTITION BY sp.symbol ORDER BY sp.date)) / LAG(sp.close, 5) OVER (PARTITION BY sp.symbol ORDER BY sp.date) * 100)::DECIMAL(5,2) as price_change_5d,
    ((sp.close - LAG(sp.close, 30) OVER (PARTITION BY sp.symbol ORDER BY sp.date)) / LAG(sp.close, 30) OVER (PARTITION BY sp.symbol ORDER BY sp.date) * 100)::DECIMAL(5,2) as price_change_30d,
    (25 + random() * 30)::DECIMAL(5,2) as volatility_30d,
    NULL::BIGINT as market_cap,
    (sp.close / NULLIF(
        (SELECT SUM(actual_eps)
         FROM (SELECT actual_eps FROM earnings e2
               WHERE e2.symbol = sp.symbol
               ORDER BY e2.report_date DESC LIMIT 4) sub),
        0))::DECIMAL(8,2) as pe_ratio,
    CURRENT_DATE as score_date,
    CURRENT_TIMESTAMP as last_updated
FROM stock_prices sp
INNER JOIN technical_data_daily td ON sp.symbol = td.symbol AND sp.date = td.date
WHERE sp.date = CURRENT_DATE - INTERVAL '1 day'
AND sp.symbol IN ('AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'META', 'AMZN', 'NFLX', 'AMD', 'CRM',
                  'JPM', 'BAC', 'KO', 'PG', 'JNJ', 'SPY', 'QQQ', 'VTI', 'IWM', 'GLD')
ON CONFLICT (symbol) DO UPDATE SET
    composite_score = EXCLUDED.composite_score,
    momentum_score = EXCLUDED.momentum_score,
    trend_score = EXCLUDED.trend_score,
    value_score = EXCLUDED.value_score,
    quality_score = EXCLUDED.quality_score,
    growth_score = EXCLUDED.growth_score,
    rsi = EXCLUDED.rsi,
    macd = EXCLUDED.macd,
    sma_20 = EXCLUDED.sma_20,
    sma_50 = EXCLUDED.sma_50,
    volume_avg_30d = EXCLUDED.volume_avg_30d,
    current_price = EXCLUDED.current_price,
    price_change_1d = EXCLUDED.price_change_1d,
    price_change_5d = EXCLUDED.price_change_5d,
    price_change_30d = EXCLUDED.price_change_30d,
    volatility_30d = EXCLUDED.volatility_30d,
    market_cap = EXCLUDED.market_cap,
    pe_ratio = EXCLUDED.pe_ratio,
    score_date = EXCLUDED.score_date,
    last_updated = EXCLUDED.last_updated;

-- =============================================
-- SECTION 5: ECONOMIC DATA with proper titles
-- Emulates: loadecondata.py loader
-- =============================================

-- Create economic_series table for metadata
CREATE TABLE IF NOT EXISTS economic_series (
    series_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    units TEXT,
    frequency TEXT,
    seasonal_adjustment TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert economic series metadata
INSERT INTO economic_series (series_id, title, units, frequency, seasonal_adjustment) VALUES
('GDP', 'Gross Domestic Product', 'Billions of Dollars', 'Quarterly', 'Seasonally Adjusted Annual Rate'),
('GDPC1', 'Real Gross Domestic Product', 'Billions of Chained 2017 Dollars', 'Quarterly', 'Seasonally Adjusted Annual Rate'),
('CPIAUCSL', 'Consumer Price Index for All Urban Consumers: All Items', 'Index 1982-1984=100', 'Monthly', 'Seasonally Adjusted'),
('UNRATE', 'Unemployment Rate', 'Percent', 'Monthly', 'Seasonally Adjusted'),
('FEDFUNDS', 'Federal Funds Effective Rate', 'Percent', 'Monthly', 'Not Seasonally Adjusted'),
('VIXCLS', 'CBOE Volatility Index: VIX', 'Index', 'Daily', 'Not Applicable'),
('DGS10', '10-Year Treasury Constant Maturity Rate', 'Percent', 'Daily', 'Not Seasonally Adjusted'),
('DEXUSEU', 'U.S. / Euro Foreign Exchange Rate', 'U.S. Dollars to One Euro', 'Daily', 'Not Seasonally Adjusted'),
('DCOILWTICO', 'Crude Oil Prices: West Texas Intermediate (WTI)', 'Dollars per Barrel', 'Daily', 'Not Seasonally Adjusted'),
('GOLDAMGBD228NLBM', 'Gold Fixing Price', 'U.S. Dollars per Troy Ounce', 'Daily', 'Not Seasonally Adjusted'),
('PAYEMS', 'All Employees: Total Nonfarm', 'Thousands of Persons', 'Monthly', 'Seasonally Adjusted'),
('ICSA', 'Initial Claims', 'Number', 'Weekly', 'Seasonally Adjusted')
ON CONFLICT (series_id) DO UPDATE SET
    title = EXCLUDED.title,
    units = EXCLUDED.units,
    frequency = EXCLUDED.frequency,
    seasonal_adjustment = EXCLUDED.seasonal_adjustment,
    last_updated = CURRENT_TIMESTAMP;

-- Generate comprehensive economic data (last 2 years)
DO $$
DECLARE
    dt DATE;
    base_gdp DECIMAL := 27000000;
    base_cpi DECIMAL := 307.789;
    base_unrate DECIMAL := 3.7;
    base_fedfunds DECIMAL := 5.25;
    base_vix DECIMAL := 15.39;
    base_dgs10 DECIMAL := 4.25;
    base_forex DECIMAL := 1.08;
    base_oil DECIMAL := 78.50;
    base_gold DECIMAL := 2065.00;
    base_payems DECIMAL := 157500;
    base_icsa DECIMAL := 210000;
BEGIN
    -- GDP (Quarterly)
    FOR dt IN SELECT generate_series(CURRENT_DATE - INTERVAL '24 months', CURRENT_DATE, '3 months'::interval)::date LOOP
        INSERT INTO economic_data (series_id, date, value)
        VALUES ('GDP', dt, base_gdp + (random() - 0.5) * base_gdp * 0.02);
        INSERT INTO economic_data (series_id, date, value)
        VALUES ('GDPC1', dt, base_gdp * 0.83 + (random() - 0.5) * base_gdp * 0.02);
    END LOOP;

    -- Monthly indicators
    FOR dt IN SELECT generate_series(CURRENT_DATE - INTERVAL '24 months', CURRENT_DATE, '1 month'::interval)::date LOOP
        INSERT INTO economic_data (series_id, date, value)
        VALUES ('CPIAUCSL', dt, base_cpi + (random() - 0.5) * 2);
        INSERT INTO economic_data (series_id, date, value)
        VALUES ('UNRATE', dt, base_unrate + (random() - 0.5) * 0.5);
        INSERT INTO economic_data (series_id, date, value)
        VALUES ('FEDFUNDS', dt, base_fedfunds + (random() - 0.5) * 0.25);
        INSERT INTO economic_data (series_id, date, value)
        VALUES ('PAYEMS', dt, base_payems + (random() - 0.5) * base_payems * 0.01);
    END LOOP;

    -- Daily indicators (last 90 days)
    FOR dt IN SELECT generate_series(CURRENT_DATE - INTERVAL '90 days', CURRENT_DATE, '1 day'::interval)::date LOOP
        IF EXTRACT(DOW FROM dt) NOT IN (0, 6) THEN  -- Skip weekends
            INSERT INTO economic_data (series_id, date, value)
            VALUES ('VIXCLS', dt, base_vix + (random() - 0.5) * 5);
            INSERT INTO economic_data (series_id, date, value)
            VALUES ('DGS10', dt, base_dgs10 + (random() - 0.5) * 0.3);
            INSERT INTO economic_data (series_id, date, value)
            VALUES ('DEXUSEU', dt, base_forex + (random() - 0.5) * 0.05);
            INSERT INTO economic_data (series_id, date, value)
            VALUES ('DCOILWTICO', dt, base_oil + (random() - 0.5) * 8);
            INSERT INTO economic_data (series_id, date, value)
            VALUES ('GOLDAMGBD228NLBM', dt, base_gold + (random() - 0.5) * 50);
        END IF;
    END LOOP;

    -- Weekly indicators (last 52 weeks)
    FOR dt IN SELECT generate_series(CURRENT_DATE - INTERVAL '52 weeks', CURRENT_DATE, '1 week'::interval)::date LOOP
        INSERT INTO economic_data (series_id, date, value)
        VALUES ('ICSA', dt, base_icsa + (random() - 0.5) * base_icsa * 0.1);
    END LOOP;

    RAISE NOTICE 'Generated comprehensive economic data';
END $$;

-- =============================================
-- Summary and Verification
-- =============================================

-- Verify data counts
DO $$
DECLARE
    price_count INTEGER;
    tech_count INTEGER;
    score_count INTEGER;
    earnings_count INTEGER;
    econ_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO price_count FROM stock_prices;
    SELECT COUNT(*) INTO tech_count FROM technical_data_daily;
    SELECT COUNT(*) INTO score_count FROM stock_scores;
    SELECT COUNT(*) INTO earnings_count FROM earnings;
    SELECT COUNT(*) INTO econ_count FROM economic_data;

    RAISE NOTICE '========================================';
    RAISE NOTICE 'DATA GENERATION SUMMARY';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Stock Prices: % records', price_count;
    RAISE NOTICE 'Technical Indicators: % records', tech_count;
    RAISE NOTICE 'Stock Scores: % records', score_count;
    RAISE NOTICE 'Earnings Data: % records', earnings_count;
    RAISE NOTICE 'Economic Data: % records', econ_count;
    RAISE NOTICE '========================================';
END $$;

COMMIT;
