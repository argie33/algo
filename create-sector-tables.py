import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2

load_dotenv(Path('.') / '.env.local')

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor()

# Create sector_ranking - what the sectors endpoint expects
sql = """
DROP TABLE IF EXISTS sector_ranking CASCADE;
CREATE TABLE sector_ranking (
    id SERIAL PRIMARY KEY,
    sector_name VARCHAR(100),
    sector VARCHAR(100),
    rank INT,
    performance FLOAT,
    ytd_performance FLOAT,
    price_change FLOAT,
    volume BIGINT,
    market_cap BIGINT,
    date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DROP TABLE IF EXISTS sector_performance CASCADE;
CREATE TABLE sector_performance (
    id SERIAL PRIMARY KEY,
    sector VARCHAR(100),
    performance FLOAT,
    date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sector_ranking_sector ON sector_ranking(sector_name, date DESC);
CREATE INDEX IF NOT EXISTS idx_sector_ranking_date ON sector_ranking(date DESC);
CREATE INDEX IF NOT EXISTS idx_sector_performance_sector ON sector_performance(sector, date DESC);

INSERT INTO sector_ranking (sector_name, sector, rank, performance, ytd_performance, price_change, volume, market_cap, date) VALUES
('Technology', 'Technology', 1, 15.5, 12.3, 2.1, 1000000, 50000000000, CURRENT_DATE),
('Healthcare', 'Healthcare', 2, 8.2, 5.4, 1.2, 800000, 45000000000, CURRENT_DATE),
('Financials', 'Financials', 3, 5.1, 3.2, 0.8, 900000, 40000000000, CURRENT_DATE),
('Consumer Discretionary', 'Consumer Discretionary', 4, 3.5, 2.1, 0.5, 700000, 35000000000, CURRENT_DATE),
('Industrials', 'Industrials', 5, 2.8, 1.9, 0.4, 600000, 30000000000, CURRENT_DATE),
('Energy', 'Energy', 6, -5.2, -3.1, -0.9, 500000, 25000000000, CURRENT_DATE),
('Utilities', 'Utilities', 7, -2.1, -1.5, -0.3, 400000, 20000000000, CURRENT_DATE),
('Real Estate', 'Real Estate', 8, -8.5, -6.2, -1.3, 300000, 15000000000, CURRENT_DATE),
('Consumer Staples', 'Consumer Staples', 9, 1.2, 0.8, 0.2, 350000, 18000000000, CURRENT_DATE),
('Materials', 'Materials', 10, -3.4, -2.1, -0.6, 250000, 12000000000, CURRENT_DATE),
('Communication Services', 'Communication Services', 11, 6.7, 4.5, 1.1, 550000, 28000000000, CURRENT_DATE);

INSERT INTO sector_performance (sector, performance, date) VALUES
('Technology', 15.5, CURRENT_DATE),
('Healthcare', 8.2, CURRENT_DATE),
('Financials', 5.1, CURRENT_DATE),
('Consumer Discretionary', 3.5, CURRENT_DATE),
('Industrials', 2.8, CURRENT_DATE),
('Energy', -5.2, CURRENT_DATE),
('Utilities', -2.1, CURRENT_DATE),
('Real Estate', -8.5, CURRENT_DATE),
('Consumer Staples', 1.2, CURRENT_DATE),
('Materials', -3.4, CURRENT_DATE),
('Communication Services', 6.7, CURRENT_DATE);
"""

try:
    cursor.execute(sql)
    conn.commit()
    print("Created sector tables with seed data")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()

conn.close()
