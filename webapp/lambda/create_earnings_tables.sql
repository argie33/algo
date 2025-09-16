-- Create comprehensive earnings and calendar tables

-- Enhanced earnings_reports table with all necessary columns
CREATE TABLE IF NOT EXISTS earnings_reports (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    company_name VARCHAR(255),
    report_date DATE NOT NULL,
    quarter INTEGER,
    fiscal_year INTEGER,
    announcement_date DATE,
    estimated_eps DECIMAL(10,4),
    actual_eps DECIMAL(10,4),
    eps_surprise DECIMAL(10,4),
    surprise_percent DECIMAL(5,2),
    estimated_revenue BIGINT,
    actual_revenue BIGINT,
    revenue_surprise_percent DECIMAL(5,2),
    guidance_eps_low DECIMAL(10,4),
    guidance_eps_high DECIMAL(10,4),
    guidance_revenue_low BIGINT,
    guidance_revenue_high BIGINT,
    conference_call_time TIMESTAMP,
    timing VARCHAR(20), -- 'before_market', 'after_market', 'market_hours'
    analyst_count INTEGER DEFAULT 0,
    revision_trend VARCHAR(10), -- 'up', 'down', 'stable'
    earnings_score DECIMAL(3,2) DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, report_date)
);

-- Economic events table
CREATE TABLE IF NOT EXISTS economic_events (
    id SERIAL PRIMARY KEY,
    event_name VARCHAR(255) NOT NULL,
    country VARCHAR(10) NOT NULL,
    currency VARCHAR(5),
    category VARCHAR(50),
    importance VARCHAR(10), -- 'high', 'medium', 'low'
    event_time TIMESTAMP NOT NULL,
    forecast_value VARCHAR(50),
    previous_value VARCHAR(50),
    actual_value VARCHAR(50),
    impact VARCHAR(10), -- 'high', 'medium', 'low'
    unit VARCHAR(20),
    source VARCHAR(100),
    description TEXT,
    is_revised BOOLEAN DEFAULT FALSE,
    is_tentative BOOLEAN DEFAULT FALSE,
    volatility_expected VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(event_name, country, event_time)
);

-- Dividend events table
CREATE TABLE IF NOT EXISTS dividend_events (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    ex_dividend_date DATE NOT NULL,
    record_date DATE,
    payment_date DATE,
    announcement_date DATE,
    dividend_amount DECIMAL(10,4),
    dividend_yield DECIMAL(5,2),
    dividend_type VARCHAR(20) DEFAULT 'Regular Cash',
    frequency VARCHAR(20), -- 'Monthly', 'Quarterly', 'Semi-Annual', 'Annual'
    currency VARCHAR(5) DEFAULT 'USD',
    is_special BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, ex_dividend_date)
);

-- Calendar events unified view
CREATE TABLE IF NOT EXISTS calendar_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(20) NOT NULL, -- 'earnings', 'dividend', 'economic', 'split'
    symbol VARCHAR(10), -- NULL for economic events
    title VARCHAR(255) NOT NULL,
    description TEXT,
    start_date DATE NOT NULL,
    end_date DATE,
    start_time TIMESTAMP,
    all_day BOOLEAN DEFAULT FALSE,
    importance VARCHAR(10), -- 'high', 'medium', 'low'
    category VARCHAR(50),
    data_source VARCHAR(50),
    external_id VARCHAR(100),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_earnings_reports_symbol ON earnings_reports(symbol);
CREATE INDEX IF NOT EXISTS idx_earnings_reports_date ON earnings_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_earnings_reports_symbol_date ON earnings_reports(symbol, report_date);

CREATE INDEX IF NOT EXISTS idx_economic_events_time ON economic_events(event_time);
CREATE INDEX IF NOT EXISTS idx_economic_events_country ON economic_events(country);
CREATE INDEX IF NOT EXISTS idx_economic_events_importance ON economic_events(importance);

CREATE INDEX IF NOT EXISTS idx_dividend_events_symbol ON dividend_events(symbol);
CREATE INDEX IF NOT EXISTS idx_dividend_events_ex_date ON dividend_events(ex_dividend_date);

CREATE INDEX IF NOT EXISTS idx_calendar_events_type ON calendar_events(event_type);
CREATE INDEX IF NOT EXISTS idx_calendar_events_date ON calendar_events(start_date);
CREATE INDEX IF NOT EXISTS idx_calendar_events_symbol ON calendar_events(symbol);

-- Insert some sample earnings data for major stocks
INSERT INTO earnings_reports (
    symbol, company_name, report_date, quarter, fiscal_year,
    estimated_eps, actual_eps, eps_surprise, surprise_percent,
    estimated_revenue, actual_revenue, timing, analyst_count
) VALUES 
-- Current quarter upcoming earnings
('AAPL', 'Apple Inc.', CURRENT_DATE + INTERVAL '5 days', 1, 2024, 2.11, NULL, NULL, NULL, 124500000000, NULL, 'after_market', 28),
('MSFT', 'Microsoft Corporation', CURRENT_DATE + INTERVAL '8 days', 1, 2024, 2.78, NULL, NULL, NULL, 56100000000, NULL, 'after_market', 32),
('GOOGL', 'Alphabet Inc.', CURRENT_DATE + INTERVAL '12 days', 1, 2024, 1.51, NULL, NULL, NULL, 76200000000, NULL, 'after_market', 25),
('AMZN', 'Amazon.com Inc.', CURRENT_DATE + INTERVAL '15 days', 1, 2024, 0.87, NULL, NULL, NULL, 148500000000, NULL, 'after_market', 30),
('TSLA', 'Tesla Inc.', CURRENT_DATE + INTERVAL '18 days', 1, 2024, 0.85, NULL, NULL, NULL, 24300000000, NULL, 'after_market', 22),
('NVDA', 'NVIDIA Corporation', CURRENT_DATE + INTERVAL '20 days', 4, 2023, 4.64, NULL, NULL, NULL, 18100000000, NULL, 'after_market', 27),
('META', 'Meta Platforms Inc.', CURRENT_DATE + INTERVAL '22 days', 1, 2024, 3.87, NULL, NULL, NULL, 36900000000, NULL, 'after_market', 24),
('NFLX', 'Netflix Inc.', CURRENT_DATE + INTERVAL '25 days', 1, 2024, 2.97, NULL, NULL, NULL, 8500000000, NULL, 'after_market', 18),

-- Previous quarter historical earnings
('AAPL', 'Apple Inc.', CURRENT_DATE - INTERVAL '85 days', 4, 2023, 2.08, 2.18, 0.10, 4.8, 124300000000, 119600000000, 'after_market', 28),
('MSFT', 'Microsoft Corporation', CURRENT_DATE - INTERVAL '88 days', 4, 2023, 2.68, 2.69, 0.01, 0.4, 55800000000, 56500000000, 'after_market', 32),
('GOOGL', 'Alphabet Inc.', CURRENT_DATE - INTERVAL '82 days', 4, 2023, 1.38, 1.64, 0.26, 18.8, 75900000000, 76048000000, 'after_market', 25),
('AMZN', 'Amazon.com Inc.', CURRENT_DATE - INTERVAL '90 days', 4, 2023, 0.75, 1.00, 0.25, 33.3, 149200000000, 170000000000, 'after_market', 30),
('TSLA', 'Tesla Inc.', CURRENT_DATE - INTERVAL '78 days', 4, 2023, 0.73, 0.71, -0.02, -2.7, 24100000000, 25167000000, 'after_market', 22)

ON CONFLICT (symbol, report_date) DO UPDATE SET
    company_name = EXCLUDED.company_name,
    quarter = EXCLUDED.quarter,
    fiscal_year = EXCLUDED.fiscal_year,
    estimated_eps = EXCLUDED.estimated_eps,
    actual_eps = EXCLUDED.actual_eps,
    eps_surprise = EXCLUDED.eps_surprise,
    surprise_percent = EXCLUDED.surprise_percent,
    estimated_revenue = EXCLUDED.estimated_revenue,
    actual_revenue = EXCLUDED.actual_revenue,
    timing = EXCLUDED.timing,
    analyst_count = EXCLUDED.analyst_count,
    updated_at = NOW();

-- Insert sample economic events
INSERT INTO economic_events (
    event_name, country, currency, category, importance, event_time,
    forecast_value, previous_value, impact, unit, source, description
) VALUES 
-- Upcoming economic events
('Federal Reserve Interest Rate Decision', 'US', 'USD', 'monetary_policy', 'high', 
 CURRENT_DATE + INTERVAL '10 days' + TIME '14:00:00', '5.25-5.50%', '5.25-5.50%', 'high', 'percent', 
 'Federal Reserve', 'FOMC monetary policy decision and rate announcement'),

('Consumer Price Index (CPI)', 'US', 'USD', 'inflation', 'high',
 CURRENT_DATE + INTERVAL '7 days' + TIME '08:30:00', '3.2%', '3.1%', 'high', 'percent',
 'Bureau of Labor Statistics', 'Monthly inflation rate and cost of living changes'),

('Non-Farm Payrolls', 'US', 'USD', 'employment', 'high',
 CURRENT_DATE + INTERVAL '3 days' + TIME '08:30:00', '185K', '199K', 'high', 'jobs',
 'Bureau of Labor Statistics', 'Monthly employment report and unemployment rate'),

('GDP Growth Rate (QoQ)', 'US', 'USD', 'gdp', 'high',
 CURRENT_DATE + INTERVAL '21 days' + TIME '08:30:00', '2.1%', '2.4%', 'medium', 'percent',
 'Bureau of Economic Analysis', 'Quarterly gross domestic product growth rate'),

('ECB Interest Rate Decision', 'EU', 'EUR', 'monetary_policy', 'high',
 CURRENT_DATE + INTERVAL '14 days' + TIME '12:45:00', '4.50%', '4.50%', 'high', 'percent',
 'European Central Bank', 'European Central Bank monetary policy meeting')

ON CONFLICT (event_name, country, event_time) DO UPDATE SET
    forecast_value = EXCLUDED.forecast_value,
    previous_value = EXCLUDED.previous_value,
    description = EXCLUDED.description,
    updated_at = NOW();

-- Insert sample dividend events
INSERT INTO dividend_events (
    symbol, ex_dividend_date, record_date, payment_date, announcement_date,
    dividend_amount, dividend_yield, frequency
) VALUES 
-- Upcoming dividend events
('AAPL', CURRENT_DATE + INTERVAL '11 days', CURRENT_DATE + INTERVAL '13 days', CURRENT_DATE + INTERVAL '41 days', CURRENT_DATE - INTERVAL '25 days', 0.24, 0.55, 'Quarterly'),
('MSFT', CURRENT_DATE + INTERVAL '19 days', CURRENT_DATE + INTERVAL '21 days', CURRENT_DATE + INTERVAL '49 days', CURRENT_DATE - INTERVAL '30 days', 0.75, 0.80, 'Quarterly'),
('JNJ', CURRENT_DATE + INTERVAL '28 days', CURRENT_DATE + INTERVAL '30 days', CURRENT_DATE + INTERVAL '58 days', CURRENT_DATE - INTERVAL '20 days', 1.19, 2.89, 'Quarterly'),
('KO', CURRENT_DATE + INTERVAL '35 days', CURRENT_DATE + INTERVAL '37 days', CURRENT_DATE + INTERVAL '65 days', CURRENT_DATE - INTERVAL '15 days', 0.46, 3.16, 'Quarterly'),
('PEP', CURRENT_DATE + INTERVAL '42 days', CURRENT_DATE + INTERVAL '44 days', CURRENT_DATE + INTERVAL '72 days', CURRENT_DATE - INTERVAL '10 days', 1.15, 2.68, 'Quarterly')

ON CONFLICT (symbol, ex_dividend_date) DO UPDATE SET
    record_date = EXCLUDED.record_date,
    payment_date = EXCLUDED.payment_date,
    dividend_amount = EXCLUDED.dividend_amount,
    dividend_yield = EXCLUDED.dividend_yield;

-- Populate unified calendar_events table from other tables
INSERT INTO calendar_events (event_type, symbol, title, description, start_date, start_time, importance, category, data_source, metadata)
SELECT 
    'earnings' as event_type,
    symbol,
    company_name || ' Q' || quarter || ' ' || fiscal_year || ' Earnings' as title,
    'Quarterly earnings report - estimated EPS: $' || estimated_eps as description,
    report_date as start_date,
    report_date + CASE WHEN timing = 'before_market' THEN TIME '09:30:00' ELSE TIME '16:00:00' END as start_time,
    'high' as importance,
    'earnings' as category,
    'earnings_reports' as data_source,
    json_build_object(
        'estimated_eps', estimated_eps,
        'actual_eps', actual_eps,
        'timing', timing,
        'analyst_count', analyst_count
    ) as metadata
FROM earnings_reports
WHERE report_date >= CURRENT_DATE - INTERVAL '7 days'

UNION ALL

SELECT 
    'economic' as event_type,
    NULL as symbol,
    event_name as title,
    description,
    event_time::date as start_date,
    event_time as start_time,
    importance,
    category,
    'economic_events' as data_source,
    json_build_object(
        'country', country,
        'currency', currency,
        'forecast_value', forecast_value,
        'previous_value', previous_value,
        'impact', impact
    ) as metadata
FROM economic_events
WHERE event_time >= CURRENT_DATE - INTERVAL '1 day'

UNION ALL

SELECT 
    'dividend' as event_type,
    symbol,
    symbol || ' Ex-Dividend (' || dividend_type || ')' as title,
    'Ex-dividend date - Amount: $' || dividend_amount || ' (Yield: ' || dividend_yield || '%)' as description,
    ex_dividend_date as start_date,
    ex_dividend_date + TIME '09:30:00' as start_time,
    'medium' as importance,
    'dividend' as category,
    'dividend_events' as data_source,
    json_build_object(
        'dividend_amount', dividend_amount,
        'dividend_yield', dividend_yield,
        'frequency', frequency,
        'payment_date', payment_date
    ) as metadata
FROM dividend_events
WHERE ex_dividend_date >= CURRENT_DATE - INTERVAL '7 days'

ON CONFLICT DO NOTHING;

COMMIT;