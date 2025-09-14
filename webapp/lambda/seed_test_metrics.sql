-- Insert test data for AAPL and MSFT metrics using correct column names
INSERT INTO stock_scores (symbol, date, fundamental_score, technical_score, sentiment_score, overall_score, grade) VALUES
('AAPL', CURRENT_DATE, 0.95, 0.80, 0.70, 0.88, 'A'),
('MSFT', CURRENT_DATE, 0.92, 0.75, 0.72, 0.85, 'A')
ON CONFLICT (symbol, date) DO UPDATE SET
  fundamental_score = EXCLUDED.fundamental_score,
  technical_score = EXCLUDED.technical_score,
  sentiment_score = EXCLUDED.sentiment_score,
  overall_score = EXCLUDED.overall_score,
  grade = EXCLUDED.grade;
