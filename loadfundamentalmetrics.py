#!/usr/bin/env python3
import sys
import logging
import os
import json
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import pandas as pd

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN")

# --- DB config loader (reuse from other scripts) ---
def get_db_config():
    import boto3
    secret_str = boto3.client("secretsmanager") \
        .get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

def get_db_conn():
    cfg = get_db_config()
    return psycopg2.connect(**cfg)

# --- Table name ---
TABLE_NAME = "fundamental_metrics"

# --- Drop and create table ---
def create_table(conn):
    with conn.cursor() as cur:
        cur.execute(f"""
        DROP TABLE IF EXISTS {TABLE_NAME};
        CREATE TABLE {TABLE_NAME} (
            symbol TEXT NOT NULL,
            report_date DATE NOT NULL,
            eps_growth_1q FLOAT,
            eps_growth_2q FLOAT,
            eps_growth_4q FLOAT,
            eps_growth_8q FLOAT,
            eps_acceleration_qtrs INT,
            eps_surprise_last_q FLOAT,
            eps_estimate_revision_1m FLOAT,
            eps_estimate_revision_3m FLOAT,
            eps_estimate_revision_6m FLOAT,
            annual_eps_growth_1y FLOAT,
            annual_eps_growth_3y FLOAT,
            annual_eps_growth_5y FLOAT,
            consecutive_eps_growth_years INT,
            eps_estimated_change_this_year FLOAT,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, report_date)
        );
        """)
        conn.commit()
        logging.info(f"Table {TABLE_NAME} created.")

# --- Main loader logic ---
def main():
    conn = get_db_conn()
    create_table(conn)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # --- Load earnings data ---
    cur.execute("SELECT symbol, report_date, eps_actual, eps_estimate, eps_surprise FROM earnings_history ORDER BY symbol, report_date")
    earnings = pd.DataFrame(cur.fetchall())
    if earnings.empty:
        logging.warning("No earnings data found.")
        return

    # --- Load estimate revisions ---
    cur.execute("SELECT symbol, report_date, eps_estimate FROM earnings_estimates ORDER BY symbol, report_date")
    estimates = pd.DataFrame(cur.fetchall())

    # --- Load annual EPS ---
    cur.execute("SELECT symbol, fiscal_year, eps_actual FROM annual_earnings ORDER BY symbol, fiscal_year")
    annual = pd.DataFrame(cur.fetchall())

    # --- Calculate metrics ---
    results = []
    for symbol, group in earnings.groupby('symbol'):
        group = group.sort_values('report_date')
        # EPS growth over last X quarters
        for idx, row in group.iterrows():
            i = group.index.get_loc(idx)
            recent = group.iloc[max(0, i-7):i+1]  # up to 8 quarters
            metrics = {
                'symbol': symbol,
                'report_date': row['report_date'],
                'eps_growth_1q': None,
                'eps_growth_2q': None,
                'eps_growth_4q': None,
                'eps_growth_8q': None,
                'eps_acceleration_qtrs': None,
                'eps_surprise_last_q': row.get('eps_surprise'),
                'eps_estimate_revision_1m': None,
                'eps_estimate_revision_3m': None,
                'eps_estimate_revision_6m': None,
                'annual_eps_growth_1y': None,
                'annual_eps_growth_3y': None,
                'annual_eps_growth_5y': None,
                'consecutive_eps_growth_years': None,
                'eps_estimated_change_this_year': None
            }
            # EPS growth
            if len(recent) >= 2:
                metrics['eps_growth_1q'] = pct_change(recent['eps_actual'].iloc[-2], recent['eps_actual'].iloc[-1])
            if len(recent) >= 3:
                metrics['eps_growth_2q'] = pct_change(recent['eps_actual'].iloc[-3], recent['eps_actual'].iloc[-1])
            if len(recent) >= 5:
                metrics['eps_growth_4q'] = pct_change(recent['eps_actual'].iloc[-5], recent['eps_actual'].iloc[-1])
            if len(recent) >= 9:
                metrics['eps_growth_8q'] = pct_change(recent['eps_actual'].iloc[0], recent['eps_actual'].iloc[-1])
            # EPS acceleration: count quarters with positive growth
            growths = recent['eps_actual'].pct_change().dropna()
            metrics['eps_acceleration_qtrs'] = (growths > 0).sum()
            # Estimate revisions (1m, 3m, 6m)
            est_group = estimates[(estimates['symbol'] == symbol) & (estimates['report_date'] <= row['report_date'])]
            if not est_group.empty:
                est_now = est_group.iloc[-1]['eps_estimate']
                for months, key in [(1, 'eps_estimate_revision_1m'), (3, 'eps_estimate_revision_3m'), (6, 'eps_estimate_revision_6m')]:
                    past = est_group[est_group['report_date'] <= (pd.to_datetime(row['report_date']) - pd.DateOffset(months=months))]
                    if not past.empty:
                        metrics[key] = pct_change(past.iloc[-1]['eps_estimate'], est_now)
            results.append(metrics)
    # --- Annual EPS growth and consecutive years ---
    for symbol, group in annual.groupby('symbol'):
        group = group.sort_values('fiscal_year')
        group['eps_growth'] = group['eps_actual'].pct_change()
        group['is_growth'] = group['eps_growth'] > 0
        group['consec'] = group['is_growth'].astype(int).groupby((group['is_growth'] != group['is_growth'].shift()).cumsum()).cumsum()
        max_consec = group['consec'].max() if not group.empty else 0
        for idx, row in group.iterrows():
            # Find matching result by symbol and year
            for r in results:
                if r['symbol'] == symbol and str(row['fiscal_year']) in str(r['report_date']):
                    r['annual_eps_growth_1y'] = row['eps_growth']
                    r['consecutive_eps_growth_years'] = max_consec
        # 3y/5y growth
        if len(group) >= 4:
            results[-1]['annual_eps_growth_3y'] = pct_change(group['eps_actual'].iloc[-4], group['eps_actual'].iloc[-1])
        if len(group) >= 6:
            results[-1]['annual_eps_growth_5y'] = pct_change(group['eps_actual'].iloc[-6], group['eps_actual'].iloc[-1])
    # --- Write to DB ---
    if results:
        keys = list(results[0].keys())
        values = [[r.get(k) for k in keys] for r in results]
        with conn.cursor() as cur:
            execute_values(cur, f"INSERT INTO {TABLE_NAME} ({','.join(keys)}) VALUES %s ON CONFLICT (symbol, report_date) DO UPDATE SET " + ','.join([f"{k}=EXCLUDED.{k}" for k in keys if k not in ['symbol','report_date']]), values)
            conn.commit()
        logging.info(f"Inserted/updated {len(results)} rows into {TABLE_NAME}.")
    else:
        logging.warning("No metrics calculated.")
    conn.close()

def pct_change(old, new):
    try:
        if old is None or new is None or old == 0:
            return None
        return (new - old) / abs(old)
    except Exception:
        return None

if __name__ == "__main__":
    main()
