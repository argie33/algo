#!/usr/bin/env python3
"""
Local development script to load sample economic data into the database.
This allows testing the economic endpoints without a FRED API key.
"""
import psycopg2
from datetime import datetime, timedelta
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="stocks",
    user="postgres",
    password="password"
)
cur = conn.cursor()

# Create tables if they don't exist
cur.execute("""
    CREATE TABLE IF NOT EXISTS economic_data (
        series_id TEXT NOT NULL,
        date       DATE NOT NULL,
        value      DOUBLE PRECISION,
        PRIMARY KEY (series_id, date)
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS economic_calendar (
        id SERIAL PRIMARY KEY,
        event_id VARCHAR(50) UNIQUE,
        event_name VARCHAR(255) NOT NULL,
        country VARCHAR(10) DEFAULT 'US',
        category VARCHAR(100),
        importance VARCHAR(20) NOT NULL,
        currency VARCHAR(3) DEFAULT 'USD',
        event_date DATE NOT NULL,
        event_time TIME,
        timezone VARCHAR(50) DEFAULT 'America/New_York',
        actual_value VARCHAR(100),
        forecast_value VARCHAR(100),
        previous_value VARCHAR(100),
        unit VARCHAR(50),
        frequency VARCHAR(20),
        source VARCHAR(100),
        description TEXT,
        impact_analysis TEXT,
        is_revised BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")

conn.commit()
logger.info("✅ Tables created/verified")

# Sample data for the last 2 years
today = datetime.now().date()
sample_data = {
    'T10Y2Y': [50, 45, 40, 35, 30, 25, 20, 15, 10, 5, 0, -5, -10, -15, -20, -25, -30, -25, -20, -15],  # Yield spread
    'T10Y3M': [80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 25, 20, 15, 10, 5, 0, -5, -10, -15],  # 3m/10y spread
    'UNRATE': [4.2, 4.1, 4.0, 3.9, 3.8, 3.9, 4.0, 4.1, 4.2, 4.3, 4.2, 4.1, 4.0, 3.9, 3.8, 3.9, 4.0, 4.1, 4.2, 4.3],  # Unemployment
    'FEDFUNDS': [5.33, 5.25, 5.17, 5.08, 5.0, 4.92, 4.83, 4.75, 4.67, 4.58, 4.5, 4.42, 4.33, 4.25, 4.17, 4.08, 4.0, 3.92, 3.83, 3.75],  # Fed funds rate
    'VIXCLS': [18, 17.5, 17, 16.5, 16, 15.5, 15, 14.5, 14, 13.5, 13, 12.5, 12, 11.5, 11, 10.5, 10, 10.5, 11, 11.5],  # VIX
    'SP500': [5700, 5650, 5600, 5550, 5500, 5550, 5600, 5650, 5700, 5750, 5800, 5750, 5700, 5650, 5600, 5550, 5500, 5550, 5600, 5650],  # S&P 500
    'BAMLH0A0HYM2': [450, 440, 430, 420, 410, 400, 390, 380, 370, 360, 350, 340, 330, 320, 310, 300, 290, 300, 310, 320],  # HY spread
    'BAMLH0A0IG': [150, 145, 140, 135, 130, 125, 120, 115, 110, 105, 100, 95, 90, 85, 80, 75, 70, 75, 80, 85],  # IG spread
    'GDPC1': [28500, 28600, 28700, 28800, 28900, 29000, 29100, 29200, 29300, 29400, 29500, 29600, 29700, 29800, 29900, 30000, 30100, 30200, 30300, 30400],  # GDP
    'CIVPART': [63.2, 63.1, 63.0, 62.9, 62.8, 62.9, 63.0, 63.1, 63.2, 63.3, 63.4, 63.3, 63.2, 63.1, 63.0, 62.9, 62.8, 62.9, 63.0, 63.1],  # Labor participation
    'ICSA': [235000, 240000, 245000, 250000, 248000, 245000, 242000, 240000, 238000, 240000, 242000, 245000, 248000, 250000, 248000, 245000, 242000, 240000, 238000, 240000],  # Initial claims
    'INDPRO': [105.5, 105.6, 105.7, 105.8, 105.9, 106.0, 106.1, 106.2, 106.3, 106.4, 106.5, 106.4, 106.3, 106.2, 106.1, 106.0, 105.9, 105.8, 105.7, 105.6],  # Industrial production
    # LAGGING ECONOMIC INDICATORS
    'UEMPMEAN': [18.5, 18.2, 17.9, 17.6, 17.3, 17.5, 17.7, 17.9, 18.1, 18.3, 18.5, 18.3, 18.1, 17.9, 17.7, 17.5, 17.3, 17.5, 17.7, 17.9],  # Average duration of unemployment (weeks)
    'PRIME': [8.5, 8.45, 8.4, 8.35, 8.3, 8.25, 8.2, 8.15, 8.1, 8.05, 8.0, 7.95, 7.9, 7.85, 7.8, 7.75, 7.7, 7.75, 7.8, 7.85],  # Prime lending rate (%)
    'MMNRNJ': [5.15, 5.1, 5.05, 5.0, 4.95, 4.9, 4.85, 4.8, 4.75, 4.7, 4.65, 4.6, 4.55, 4.5, 4.45, 4.4, 4.35, 4.4, 4.45, 4.5],  # Money market rate (%)
    'ISITC': [1.32, 1.31, 1.30, 1.29, 1.28, 1.27, 1.26, 1.27, 1.28, 1.29, 1.30, 1.31, 1.32, 1.31, 1.30, 1.29, 1.28, 1.27, 1.26, 1.27],  # Inventory-sales ratio
    'TOTALSA': [158300, 158250, 158200, 158150, 158100, 158050, 158000, 157950, 157900, 157850, 157800, 157750, 157700, 157650, 157600, 157550, 157500, 157550, 157600, 157650],  # Total nonfarm payroll (thousands)
    'IMPGS': [381500, 380800, 380100, 379400, 378700, 378000, 377300, 377800, 378300, 378800, 379300, 379800, 380300, 380800, 381300, 381800, 382300, 381800, 381300, 380800],  # Imports (millions)
    'LBMVRTQ': [56.85, 56.80, 56.75, 56.70, 56.65, 56.70, 56.75, 56.80, 56.85, 56.90, 56.95, 56.90, 56.85, 56.80, 56.75, 56.70, 56.65, 56.70, 56.75, 56.80],  # Labor share of income (%)
    # COINCIDENT ECONOMIC INDICATORS
    'UMCSENT': [74.5, 74.2, 73.9, 73.6, 73.3, 73.6, 73.9, 74.2, 74.5, 74.8, 75.1, 74.8, 74.5, 74.2, 73.9, 73.6, 73.3, 73.6, 73.9, 74.2],  # Consumer sentiment index
    'RSXFS': [675200, 674800, 674400, 674000, 673600, 673900, 674200, 674500, 674800, 675100, 675400, 675100, 674800, 674500, 674200, 673900, 673600, 673900, 674200, 674500],  # Retail sales (millions)
    'EMSRATIO': [60.1, 60.15, 60.2, 60.25, 60.3, 60.25, 60.2, 60.15, 60.1, 60.05, 60.0, 60.05, 60.1, 60.15, 60.2, 60.25, 60.3, 60.25, 60.2, 60.15],  # Employment-to-population ratio (%)
}

# Insert sample data for the past 20 business days
rows = []
for i, (series_id, values) in enumerate(sample_data.items()):
    for j, value in enumerate(values):
        date = today - timedelta(days=(len(values) - 1 - j) * 5)  # Every 5 days
        rows.append((series_id, date, value))

# Upsert the data
from psycopg2.extras import execute_values
execute_values(
    cur,
    """
    INSERT INTO economic_data (series_id, date, value)
    VALUES %s
    ON CONFLICT (series_id, date) DO UPDATE
      SET value = EXCLUDED.value;
    """,
    rows
)
conn.commit()
logger.info(f"✅ Inserted {len(rows)} rows of economic data")

# Check what we have
cur.execute("SELECT COUNT(*) FROM economic_data;")
count = cur.fetchone()[0]
logger.info(f"✅ Total economic_data rows: {count}")

cur.execute("SELECT DISTINCT series_id FROM economic_data ORDER BY series_id;")
series = [row[0] for row in cur.fetchall()]
logger.info(f"✅ Series loaded: {', '.join(series)}")

cur.close()
conn.close()
logger.info("✅ Done! Economic data loaded for local development")
