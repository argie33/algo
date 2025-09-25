-- Add test data for analysts routes
-- Create analyst_upgrade_downgrade table with test data

-- Create analyst_upgrade_downgrade table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'analyst_upgrade_downgrade') THEN
        CREATE TABLE analyst_upgrade_downgrade (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            action VARCHAR(50) NOT NULL,
            firm VARCHAR(100) NOT NULL,
            date DATE NOT NULL,
            from_grade VARCHAR(50),
            to_grade VARCHAR(50),
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX idx_analyst_upgrade_symbol ON analyst_upgrade_downgrade(symbol);
        CREATE INDEX idx_analyst_upgrade_action ON analyst_upgrade_downgrade(action);
        CREATE INDEX idx_analyst_upgrade_date ON analyst_upgrade_downgrade(date DESC);

        RAISE NOTICE 'Created analyst_upgrade_downgrade table';
    ELSE
        RAISE NOTICE 'analyst_upgrade_downgrade table already exists';
    END IF;
END $$;

-- Insert test data
INSERT INTO analyst_upgrade_downgrade (symbol, action, firm, date, from_grade, to_grade, details)
VALUES
    ('AAPL', 'Upgrade', 'Goldman Sachs', CURRENT_DATE - INTERVAL '1 day', 'Hold', 'Buy', 'Strong earnings beat and positive outlook'),
    ('MSFT', 'Upgrade', 'Morgan Stanley', CURRENT_DATE - INTERVAL '2 days', 'Neutral', 'Overweight', 'Cloud growth accelerating'),
    ('GOOGL', 'Upgrade', 'JP Morgan', CURRENT_DATE - INTERVAL '3 days', 'Underweight', 'Neutral', 'Search revenue recovering'),
    ('TSLA', 'Downgrade', 'Credit Suisse', CURRENT_DATE - INTERVAL '4 days', 'Buy', 'Hold', 'Delivery concerns persist'),
    ('NVDA', 'Upgrade', 'Deutsche Bank', CURRENT_DATE - INTERVAL '5 days', 'Hold', 'Buy', 'AI demand driving growth'),
    ('META', 'Neutral', 'Barclays', CURRENT_DATE - INTERVAL '6 days', 'Overweight', 'Equal Weight', 'Metaverse spending concerns'),
    ('AMZN', 'Upgrade', 'UBS', CURRENT_DATE - INTERVAL '7 days', 'Neutral', 'Buy', 'AWS margins improving'),
    ('NFLX', 'Downgrade', 'Citigroup', CURRENT_DATE - INTERVAL '8 days', 'Buy', 'Neutral', 'Subscriber growth slowing')
ON CONFLICT DO NOTHING;

-- Create analyst_estimates table if it doesn't exist (for earnings estimates)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'analyst_estimates') THEN
        CREATE TABLE analyst_estimates (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            target_mean_price DECIMAL(10,2),
            target_high_price DECIMAL(10,2),
            target_low_price DECIMAL(10,2),
            recommendation_mean DECIMAL(3,2),
            recommendation_key VARCHAR(20),
            analyst_opinion_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX idx_analyst_estimates_ticker ON analyst_estimates(ticker);

        RAISE NOTICE 'Created analyst_estimates table';
    ELSE
        RAISE NOTICE 'analyst_estimates table already exists';
    END IF;
END $$;

-- Insert analyst estimates test data
INSERT INTO analyst_estimates (ticker, target_mean_price, target_high_price, target_low_price, recommendation_mean, recommendation_key, analyst_opinion_count)
VALUES
    ('AAPL', 185.50, 200.00, 170.00, 2.1, 'Buy', 15),
    ('MSFT', 420.75, 450.00, 390.00, 1.8, 'Strong Buy', 18),
    ('GOOGL', 145.25, 160.00, 130.00, 2.3, 'Buy', 12),
    ('TSLA', 230.00, 280.00, 180.00, 2.8, 'Hold', 20),
    ('NVDA', 485.30, 520.00, 450.00, 1.9, 'Buy', 16),
    ('META', 315.60, 340.00, 290.00, 2.4, 'Buy', 14),
    ('AMZN', 142.80, 155.00, 130.00, 2.2, 'Buy', 17),
    ('NFLX', 445.90, 480.00, 410.00, 2.6, 'Hold', 11)
ON CONFLICT DO NOTHING;

COMMIT;

-- Verification
SELECT 'analyst_upgrade_downgrade' as table_name, COUNT(*) as row_count FROM analyst_upgrade_downgrade
UNION ALL
SELECT 'analyst_estimates' as table_name, COUNT(*) as row_count FROM analyst_estimates;