"""Lambda function to seed real ICE DXY data.

CRITICAL: Fetch REAL DXY data from Yahoo Finance, never use hardcoded values.
This lambda is for backfill/initialization only. Production data comes from
loaders/load_dxy_index.py which fetches from Yahoo Finance.
"""

import json
import os
from datetime import date, timedelta

import psycopg2


def lambda_handler(event, context):
    """Seed DXY data from Yahoo Finance into database."""
    try:
        # FAIL-FAST: Require all database credentials explicitly (no defaults)
        db_host = os.environ.get("DB_HOST")
        db_port_str = os.environ.get("DB_PORT")
        db_name = os.environ.get("DB_NAME")
        db_user = os.environ.get("DB_USER")
        db_password = os.environ.get("DB_PASSWORD")

        missing = []
        if not db_host:
            missing.append("DB_HOST")
        if not db_port_str:
            missing.append("DB_PORT")
        if not db_name:
            missing.append("DB_NAME")
        if not db_user:
            missing.append("DB_USER")
        if not db_password:
            missing.append("DB_PASSWORD")

        if missing:
            raise ValueError(
                f'[CRITICAL] Missing database environment variables: {", ".join(missing)}. '
                "Cannot proceed without explicit database configuration."
            )

        # Fetch REAL DXY data from Yahoo Finance, never hardcoded values
        dxy_data = _fetch_dxy_from_yahoo()
        if not dxy_data:
            raise RuntimeError(
                "[CRITICAL] Could not fetch real DXY data from Yahoo Finance. "
                "Refusing to insert fake/placeholder values. "
                "Check Yahoo Finance API connectivity and availability."
            )

        # Connect to database
        conn = psycopg2.connect(
            host=db_host, user=db_user, password=db_password, database=db_name, port=int(db_port_str), sslmode="require"
        )
        cur = conn.cursor()

        # Delete existing DXY_ICE data to avoid duplicates
        cur.execute("DELETE FROM economic_data WHERE series_id = %s", ("DXY_ICE",))

        # Insert REAL DXY data
        inserted_count = 0
        for row in dxy_data:
            cur.execute(
                "INSERT INTO economic_data (series_id, date, value) VALUES (%s, %s, %s)",
                ("DXY_ICE", row["date"], row["value"]),
            )
            inserted_count += 1

        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps(
                {"success": True, "message": f"Seeded {inserted_count} real DXY_ICE values from Yahoo Finance"}
            ),
        }
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def _fetch_dxy_from_yahoo() -> list[dict]:
    """Fetch real ICE DXY from Yahoo Finance.

    Returns:
        list: [{"date": "2026-06-29", "value": actual_value}, ...]
        where actual_value is the real market close price from Yahoo Finance.

    Raises:
        RuntimeError: If fetch fails or returns no data
        Per governance: "Fail-fast on missing data. No silent fallbacks."
        This function will not return fake/hardcoded values.
    """
    try:
        import yfinance as yf

        end_date = date.today()
        start_date = end_date - timedelta(days=730)  # 2 years of history

        dxy = yf.download("^DXY", start=start_date, end=end_date, progress=False)

        if dxy is None or len(dxy) == 0:
            raise RuntimeError("Yahoo Finance returned no data for ^DXY")

        rows = []
        for idx, row in dxy.iterrows():
            if idx.tz_aware:
                date_str = idx.tz_localize(None).date().isoformat()
            else:
                date_str = idx.date().isoformat()

            value = float(row["Close"])
            rows.append({"date": date_str, "value": value})

        if not rows:
            raise RuntimeError("No valid DXY data extracted from yfinance")

        return rows

    except ImportError as e:
        raise RuntimeError("[CRITICAL] yfinance library not available. Cannot fetch real DXY data.") from e
    except Exception as e:
        raise RuntimeError(f"[CRITICAL] Failed to fetch DXY from Yahoo Finance: {e}") from e
