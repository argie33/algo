import logging
import os
import json
import pandas as pd
from fredapi import Fred
import boto3
import pymysql

# ─── CONFIGURATION ─────────────────────────────────────────────────────────────

# 1) Your FRED API key (set as environment variable FRED_API_KEY)
fred = Fred(api_key=os.environ["FRED_API_KEY"])

# 2) MySQL connection settings from Secrets Manager (set DB_SECRET_ARN)
sm = boto3.client("secretsmanager")
secret = sm.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
creds = json.loads(secret)

db_config = {
    'host':     creds["host"],
    'port':     int(creds.get("port", 3306)),
    'user':     creds["username"],
    'password': creds["password"],
    'database': creds["dbname"]
}
connection = pymysql.connect(**db_config)
cursor     = connection.cursor()

# 3) Create (if needed) the master table
create_table_sql = """
CREATE TABLE IF NOT EXISTS economic_data (
    series_id VARCHAR(32) NOT NULL,
    date      DATE         NOT NULL,
    value     DOUBLE,
    PRIMARY KEY (series_id, date)
);
"""
cursor.execute(create_table_sql)
connection.commit()

# ─── SERIES LIST ────────────────────────────────────────────────────────────────

series_ids = [
    # --- U.S. Output & Demand (National Accounts) ---
    "GDPC1",       # Real Gross Domestic Product
    "PCECC96",     # Real Personal Consumption Expenditures
    "GPDI",        # Real Private Domestic Investment
    "GCEC1",       # Real Government Consumption & Investment
    "EXPGSC1",     # Real Exports of Goods & Services
    "IMPGSC1",     # Real Imports of Goods & Services

    # --- U.S. Labor Market ---
    "UNRATE",      # Unemployment Rate
    "PAYEMS",      # Nonfarm Payroll Employment
    "CIVPART",     # Labor Force Participation Rate
    "CES0500000003",  # Avg Hourly Earnings, Private Sector
    "AWHAE",       # Avg Weekly Hours, Private Sector
    "JTSJOL",      # Job Openings (JOLTS)
    "ICSA",        # Initial Unemployment Claims (weekly)
    "OPHNFB",      # Output per Hour of All Persons (productivity)
    "U6RATE",      # Augmented Unemployment Rate (U-6)

    # --- U.S. Inflation & Prices ---
    "CPIAUCSL",    # CPI: All Urban Consumers, All Items
    "CPILFESL",    # CPI: All Items Less Food & Energy
    "PCEPI",       # PCE Price Index, All Items
    "PCEPILFE",    # PCE Price Index, Core
    "PPIACO",      # PPI: Final Demand
    "MICH",        # Michigan Survey 1-Yr Inflation Expectations
    "T5YIFR",      # 5-Year, 5-Year Forward Inflation Expectation

    # --- U.S. Financial & Monetary ---
    "FEDFUNDS",    # Effective Federal Funds Rate
    "DGS2",        # 2-Year Treasury Constant Maturity
    "DGS10",       # 10-Year Treasury Constant Maturity
    "T10Y2Y",      # 10-Yr Minus 2-Yr Treasury Yield Spread
    "MORTGAGE30US",# 30-Year Fixed Mortgage Rate
    "BAA",         # Moody’s Baa Corporate Bond Yield
    "AAA",         # Moody’s Aaa Corporate Bond Yield
    "SP500",       # S&P 500 Stock Price Index
    "VIXCLS",      # CBOE Volatility Index (VIX)
    "M2SL",        # M2 Money Stock
    "WALCL",       # Federal Reserve Total Assets
    "IOER",        # Interest on Excess Reserves
    "IORB",        # Interest on Required Reserves

    # --- U.S. Housing & Construction ---
    "HOUST",       # Housing Starts: Total
    "PERMIT",      # Building Permits: Total
    "CSUSHPISA",   # Case-Shiller U.S. National Home Price Index
    "RHORUSQ156N", # Homeownership Rate
    "RRVRUSQ156N", # Residential Vacancy Rate
    "USHVAC",      # U.S. Home Vacancy Rate
]

# ─── FETCH & UPSERT ALL HISTORICAL POINTS ───────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s - %(message)s")
for sid in series_ids:
    logging.info(f"Fetching {sid}…")
    try:
        ts = fred.get_series(sid)
    except Exception as e:
        logging.error(f"  ✗ failed to fetch {sid}: {e}")
        continue
    if ts is None or ts.empty:
        logging.warning(f"  – no data for {sid}")
        continue

    ts = ts.dropna()
    rows = []
    for dt, val in ts.items():
        date_str = pd.to_datetime(dt).date().isoformat()
        rows.append((sid, date_str, float(val)))

    insert_sql = """
    INSERT INTO economic_data (series_id, date, value)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE value = VALUES(value);
    """
    cursor.executemany(insert_sql, rows)
    connection.commit()
    logging.info(f"  ✓ {len(rows)} records inserted for {sid}")

# ─── CLEANUP ───────────────────────────────────────────────────────────────────

cursor.close()
connection.close()
logging.info("All selected U.S. + targeted international data loaded.")
