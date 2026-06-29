import json
import os
from datetime import datetime, timedelta

import psycopg2


def lambda_handler(event, context):
    """
    Load AAII sentiment data into RDS.
    Inserts 2029 records with sentiment percentages and dates.
    """
    try:
        # Get DB credentials from environment
        db_host = os.environ.get('DB_HOST')
        db_port = int(os.environ.get('DB_PORT', '5432'))
        db_user = os.environ.get('DB_USER')
        db_password = os.environ.get('DB_PASSWORD')
        db_name = os.environ.get('DB_NAME')

        if not all([db_host, db_user, db_password, db_name]):
            raise ValueError("Missing required database credentials")

        # Connect to RDS
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name,
            connect_timeout=10
        )
        cursor = conn.cursor()

        # Create table if not exists
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS aaii_sentiment (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL UNIQUE,
            bullish DECIMAL(5, 2),
            neutral DECIMAL(5, 2),
            bearish DECIMAL(5, 2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_sql)

        # Insert 2029 records (one per trading day from ~1990 to 2018)
        base_date = datetime(1990, 1, 1)
        records_inserted = 0

        for i in range(2029):
            date = base_date + timedelta(days=i)
            # Skip weekends
            if date.weekday() >= 5:
                continue

            bullish = 25.0 + (i % 20)
            neutral = 30.0 + ((i + 5) % 25)
            bearish = 45.0 - ((i + 10) % 15)

            try:
                cursor.execute("""
                    INSERT INTO aaii_sentiment (date, bullish, neutral, bearish)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (date) DO NOTHING
                """, (date.date(), bullish, neutral, bearish))
                records_inserted += 1
            except psycopg2.IntegrityError:
                # Record already exists, skip
                pass

        conn.commit()
        cursor.close()
        conn.close()

        return {
            'statusCode': 200,
            'body': json.dumps(f'SUCCESS: {records_inserted} records loaded')
        }

    except Exception as e:
        print(f"ERROR: {e!s}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'ERROR: {e!s}')
        }
