#!/usr/bin/env python3
"""
One-time loader for S&P 500 Earnings Per Share data
Source: multpl.com - 12-month trailing earnings per share
"""
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values

# Database connection
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "stocks")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "stocks")

def fetch_sp500_earnings():
    """Fetch S&P 500 earnings from multpl.com"""
    url = "https://www.multpl.com/s-p-500-earnings/table/by-month"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find the data table
    table = soup.find('table')
    rows = table.find_all('tr')[1:]  # Skip header

    data = []
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 2:
            date_str = cols[0].text.strip()
            value_str = cols[1].text.strip().replace('$', '').replace(',', '')

            # Parse date (format: "Jun 30, 2025")
            try:
                date_obj = datetime.strptime(date_str, "%b %d, %Y")
                value = float(value_str)
                data.append((date_obj.strftime('%Y-%m-%d'), value))
            except Exception as e:
                print(f"Skipping row: {date_str}, {value_str} - {e}")

    return data

def load_to_database(data):
    """Load S&P 500 earnings data to economic_data table"""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME
    )

    try:
        with conn.cursor() as cur:
            # Prepare data for upsert
            values = [(
                'SP500_EPS',  # series_id
                date,
                value
            ) for date, value in data]

            # Upsert query
            upsert_query = """
                INSERT INTO economic_data (series_id, date, value)
                VALUES %s
                ON CONFLICT (series_id, date)
                DO UPDATE SET
                    value = EXCLUDED.value
            """

            execute_values(cur, upsert_query, values)
            conn.commit()

            print(f"✓ Loaded {len(data)} records for SP500_EPS")

    finally:
        conn.close()

if __name__ == "__main__":
    print("Fetching S&P 500 earnings data from multpl.com...")
    data = fetch_sp500_earnings()
    print(f"Found {len(data)} records")

    print("Loading to database...")
    load_to_database(data)
    print("Done!")
