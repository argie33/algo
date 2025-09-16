-- Create earnings_reports table and populate with test data
-- This fixes the calendar API 404 issues

CREATE TABLE IF NOT EXISTS earnings_reports (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    report_date DATE NOT NULL,
    quarter INTEGER,
    year INTEGER,
    eps_estimate DECIMAL(10,4),
    eps_reported DECIMAL(10,4),
    revenue BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert test earnings data for upcoming dates
INSERT INTO earnings_reports (symbol, report_date, quarter, year, eps_estimate, eps_reported, revenue) VALUES
('AAPL', CURRENT_DATE + INTERVAL '2 days', 4, 2024, 2.35, NULL, NULL),
('GOOGL', CURRENT_DATE + INTERVAL '5 days', 4, 2024, 1.85, NULL, NULL),
('MSFT', CURRENT_DATE + INTERVAL '7 days', 4, 2024, 2.78, NULL, NULL),
('AMZN', CURRENT_DATE + INTERVAL '10 days', 4, 2024, 0.75, NULL, NULL),
('TSLA', CURRENT_DATE + INTERVAL '12 days', 4, 2024, 0.85, NULL, NULL),
('META', CURRENT_DATE + INTERVAL '15 days', 4, 2024, 4.25, NULL, NULL),
('NVDA', CURRENT_DATE + INTERVAL '18 days', 4, 2024, 5.15, NULL, NULL),
('NFLX', CURRENT_DATE + INTERVAL '21 days', 4, 2024, 3.45, NULL, NULL),
('JPM', CURRENT_DATE + INTERVAL '3 days', 4, 2024, 4.05, NULL, NULL),
('JNJ', CURRENT_DATE + INTERVAL '8 days', 4, 2024, 2.65, NULL, NULL),
('WMT', CURRENT_DATE + INTERVAL '14 days', 4, 2024, 1.75, NULL, NULL),
('PG', CURRENT_DATE + INTERVAL '17 days', 4, 2024, 1.85, NULL, NULL),
('KO', CURRENT_DATE + INTERVAL '20 days', 4, 2024, 0.68, NULL, NULL),
('V', CURRENT_DATE + INTERVAL '6 days', 4, 2024, 2.35, NULL, NULL),
('UNH', CURRENT_DATE + INTERVAL '11 days', 4, 2024, 6.85, NULL, NULL),
-- Next week earnings
('BA', CURRENT_DATE + INTERVAL '8 days', 4, 2024, -0.45, NULL, NULL),
('HD', CURRENT_DATE + INTERVAL '9 days', 4, 2024, 3.78, NULL, NULL),
('PFE', CURRENT_DATE + INTERVAL '13 days', 4, 2024, 0.45, NULL, NULL),
('IBM', CURRENT_DATE + INTERVAL '16 days', 4, 2024, 2.15, NULL, NULL),
('DIS', CURRENT_DATE + INTERVAL '19 days', 4, 2024, 1.25, NULL, NULL);

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_earnings_reports_date ON earnings_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_earnings_reports_symbol ON earnings_reports(symbol);

GRANT ALL PRIVILEGES ON earnings_reports TO stocks;
GRANT ALL PRIVILEGES ON earnings_reports_id_seq TO stocks;