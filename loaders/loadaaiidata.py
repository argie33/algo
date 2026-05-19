#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
AAII Investor Sentiment Loader.

Downloads the public weekly AAII Investor Sentiment Survey spreadsheet
and stores bullish/neutral/bearish percentages in the aaii_sentiment table.

Run:
    python3 loadaaiidata.py
"""

import io
import logging
from datetime import date, datetime
from typing import List, Optional

import requests

from config.env_loader import load_env
from utils.db_connection import get_db_connection

log = logging.getLogger(__name__)

# AAII publishes their weekly survey as a public spreadsheet
AAII_URL = "https://www.aaii.com/files/surveys/sentiment.xls"


def fetch_aaii_sentiment() -> List[dict]:
    """Download and parse AAII sentiment spreadsheet."""
    try:
        resp = requests.get(AAII_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        log.error("AAII download failed: %s", e)
        return []

    try:
        import xlrd
        wb = xlrd.open_workbook(file_contents=resp.content)
        ws = wb.sheet_by_index(0)
    except ImportError:
        log.error("xlrd not installed — cannot parse AAII xls file")
        return []
    except Exception as e:
        log.error("AAII spreadsheet parse failed: %s", e)
        return []

    rows = []
    # Skip header rows — find first row with a recognizable date
    for row_idx in range(ws.nrows):
        try:
            cell = ws.cell(row_idx, 0)
            # xlrd date cells are stored as floats
            if cell.ctype == xlrd.XL_CELL_DATE:
                dt_tuple = xlrd.xldate_as_tuple(cell.value, wb.datemode)
                dt = date(*dt_tuple[:3])
            elif cell.ctype == xlrd.XL_CELL_NUMBER:
                dt_tuple = xlrd.xldate_as_tuple(cell.value, wb.datemode)
                dt = date(*dt_tuple[:3])
            elif cell.ctype == xlrd.XL_CELL_TEXT:
                # Try parsing text date
                for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
                    try:
                        dt = datetime.strptime(cell.value.strip(), fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    continue
            else:
                continue

            # Columns: date, bullish, neutral, bearish (order may vary; try 1,2,3)
            def get_pct(col):
                c = ws.cell(row_idx, col)
                if c.ctype in (xlrd.XL_CELL_NUMBER, xlrd.XL_CELL_TEXT):
                    v = float(c.value) if c.ctype == xlrd.XL_CELL_NUMBER else float(str(c.value).replace('%', ''))
                    # Normalize to 0-100 if stored as decimal (e.g. 0.45 -> 45)
                    return v * 100 if v < 1.5 else v
                return None

            bullish = get_pct(1)
            neutral = get_pct(2)
            bearish = get_pct(3)

            if bullish is None and neutral is None and bearish is None:
                continue

            rows.append({
                "date": str(dt),
                "bullish": bullish,
                "neutral": neutral,
                "bearish": bearish,
            })
        except Exception:
            continue

    log.info("AAII: parsed %d rows", len(rows))
    return rows


def upsert_rows(rows: List[dict]) -> int:
    """Upsert rows into aaii_sentiment."""
    if not rows:
        return 0
    conn = get_db_connection()
    cur = conn.cursor()
    inserted = 0
    try:
        for row in rows:
            cur.execute(
                """
                INSERT INTO aaii_sentiment (date, bullish, neutral, bearish)
                VALUES (%(date)s, %(bullish)s, %(neutral)s, %(bearish)s)
                ON CONFLICT (date) DO UPDATE SET
                    bullish = EXCLUDED.bullish,
                    neutral = EXCLUDED.neutral,
                    bearish = EXCLUDED.bearish
                """,
                row,
            )
            inserted += cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    return inserted


def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    rows = fetch_aaii_sentiment()
    if not rows:
        log.warning("No AAII data fetched — source may be unavailable")
        return 0  # Non-fatal: AAII site can be flaky

    inserted = upsert_rows(rows)
    log.info("AAII sentiment: %d rows upserted", inserted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
