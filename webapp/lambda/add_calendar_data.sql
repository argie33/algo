-- Add sample calendar/earnings data to fix calendar API endpoints

-- Add sample earnings reports for upcoming dates
INSERT INTO earnings_reports (symbol, report_date, quarter, year, revenue, net_income, eps_reported, eps_estimate, surprise_percent)
VALUES 
    ('AAPL', CURRENT_DATE + INTERVAL '2 days', 4, 2025, 123500000000, 35000000000, 6.20, 6.10, 1.64),
    ('AAPL', CURRENT_DATE + INTERVAL '5 days', 1, 2026, 128000000000, 38000000000, 6.45, 6.25, 3.20),
    ('MSFT', CURRENT_DATE + INTERVAL '3 days', 4, 2025, 65000000000, 22000000000, 11.20, 10.95, 2.28),
    ('MSFT', CURRENT_DATE + INTERVAL '7 days', 1, 2026, 68000000000, 24000000000, 11.85, 11.50, 3.04),
    ('GOOGL', CURRENT_DATE + INTERVAL '4 days', 4, 2025, 88000000000, 21000000000, 6.85, 6.65, 3.01),
    ('GOOGL', CURRENT_DATE + INTERVAL '10 days', 1, 2026, 92000000000, 23000000000, 7.20, 7.00, 2.86),
    ('META', CURRENT_DATE + INTERVAL '6 days', 4, 2025, 42000000000, 15000000000, 5.95, 5.75, 3.48),
    ('TSLA', CURRENT_DATE + INTERVAL '8 days', 4, 2025, 28000000000, 3500000000, 2.45, 2.30, 6.52),
    ('NVDA', CURRENT_DATE + INTERVAL '12 days', 4, 2025, 35000000000, 18000000000, 12.85, 12.50, 2.80),
    ('AMZN', CURRENT_DATE + INTERVAL '15 days', 4, 2025, 158000000000, 12000000000, 3.85, 3.70, 4.05)
ON CONFLICT (symbol, report_date) DO UPDATE SET
    revenue = EXCLUDED.revenue,
    net_income = EXCLUDED.net_income,
    eps_reported = EXCLUDED.eps_reported,
    eps_estimate = EXCLUDED.eps_estimate,
    surprise_percent = EXCLUDED.surprise_percent;

-- Add some historical earnings for context
INSERT INTO earnings_reports (symbol, report_date, quarter, year, revenue, net_income, eps_reported, eps_estimate, surprise_percent)
VALUES 
    ('AAPL', CURRENT_DATE - INTERVAL '30 days', 3, 2025, 119500000000, 33000000000, 5.95, 5.85, 1.71),
    ('MSFT', CURRENT_DATE - INTERVAL '25 days', 3, 2025, 62000000000, 20000000000, 10.85, 10.70, 1.40),
    ('GOOGL', CURRENT_DATE - INTERVAL '35 days', 3, 2025, 84000000000, 19000000000, 6.45, 6.25, 3.20)
ON CONFLICT (symbol, report_date) DO UPDATE SET
    revenue = EXCLUDED.revenue,
    net_income = EXCLUDED.net_income,
    eps_reported = EXCLUDED.eps_reported,
    eps_estimate = EXCLUDED.eps_estimate,
    surprise_percent = EXCLUDED.surprise_percent;

-- Add some dividend calendar entries
INSERT INTO dividend_calendar (symbol, company_name, ex_date, record_date, pay_date, dividend_amount, frequency, yield_percent)
VALUES 
    ('AAPL', 'Apple Inc.', CURRENT_DATE + INTERVAL '10 days', CURRENT_DATE + INTERVAL '12 days', CURRENT_DATE + INTERVAL '25 days', 0.25, 'Quarterly', 0.45),
    ('MSFT', 'Microsoft Corporation', CURRENT_DATE + INTERVAL '15 days', CURRENT_DATE + INTERVAL '17 days', CURRENT_DATE + INTERVAL '30 days', 0.75, 'Quarterly', 0.68),
    ('GOOGL', 'Alphabet Inc.', CURRENT_DATE + INTERVAL '20 days', CURRENT_DATE + INTERVAL '22 days', CURRENT_DATE + INTERVAL '35 days', 0.00, 'None', 0.00),
    ('META', 'Meta Platforms Inc.', CURRENT_DATE + INTERVAL '18 days', CURRENT_DATE + INTERVAL '20 days', CURRENT_DATE + INTERVAL '33 days', 0.50, 'Quarterly', 0.35),
    ('TSLA', 'Tesla Inc.', CURRENT_DATE + INTERVAL '25 days', CURRENT_DATE + INTERVAL '27 days', CURRENT_DATE + INTERVAL '40 days', 0.00, 'None', 0.00)
ON CONFLICT (symbol, ex_date) DO UPDATE SET
    company_name = EXCLUDED.company_name,
    record_date = EXCLUDED.record_date,
    pay_date = EXCLUDED.pay_date,
    dividend_amount = EXCLUDED.dividend_amount,
    frequency = EXCLUDED.frequency,
    yield_percent = EXCLUDED.yield_percent;

COMMIT;