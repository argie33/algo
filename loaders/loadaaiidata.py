#!/usr/bin/env python3
"""AAII Investor Sentiment Loader — weekly bullish/bearish/neutral survey data.

Downloads public Excel from AAII website. No API key required.
Table: aaii_sentiment (date, bullish, neutral, bearish)

Run: python3 loaders/loadaaiidata.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import io
import logging

import requests

from config.env_loader import load_env

log = logging.getLogger(__name__)

AAII_URL = "https://www.aaii.com/files/surveys/sentiment.xls"


def run() -> int:
    from utils.db_connection import get_db_connection

    log.info("Fetching AAII sentiment Excel from %s", AAII_URL)
    try:
        resp = requests.get(
            AAII_URL, timeout=60,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AlgoBot/1.0)"},
        )
        resp.raise_for_status()
        content = resp.content
    except Exception as e:
        log.warning("AAII download failed (non-fatal): %s", e)
        return 0  # Non-fatal: AAII sometimes restricts downloads

    rows = []
    try:
        import xlrd
        wb = xlrd.open_workbook(file_contents=content)
        ws = None
        for name in wb.sheet_names():
            if "sentiment" in name.lower() or "data" in name.lower():
                ws = wb.sheet_by_name(name)
                break
        if ws is None:
            ws = wb.sheet_by_index(0)

        header_row = None
        col_map = {}
        for rx in range(ws.nrows):
            row = ws.row_values(rx)
            if header_row is None:
                for i, cell in enumerate(row):
                    cs = str(cell).strip().lower()
                    if cs in ("date", "week"):
                        header_row = rx
                        col_map["date"] = i
                    elif "bull" in cs:
                        col_map["bullish"] = i
                    elif "neutral" in cs:
                        col_map["neutral"] = i
                    elif "bear" in cs:
                        col_map["bearish"] = i
                continue
            if not row or row[0] == "":
                continue
            try:
                raw = row[col_map.get("date", 0)]
                if isinstance(raw, float) and raw > 0:
                    import xlrd as xlrd_mod
                    dt = xlrd_mod.xldate_as_datetime(raw, wb.datemode)
                    d = dt.date().isoformat()
                else:
                    d = str(raw)[:10]

                bull = row[col_map.get("bullish", 1)]
                neut = row[col_map.get("neutral", 2)]
                bear = row[col_map.get("bearish", 3)]

                def _pct(v):
                    try:
                        f = float(v)
                        return f if f <= 1.0 else f / 100.0
                    except (TypeError, ValueError):
                        return None

                rows.append({
                    "date": d,
                    "bullish": _pct(bull),
                    "neutral": _pct(neut),
                    "bearish": _pct(bear),
                })
            except Exception as e:
                log.debug("Skipping AAII row: %s", e)

    except ImportError:
        log.warning("xlrd not installed — trying pandas")
        try:
            import pandas as pd
            df = pd.read_excel(io.BytesIO(content))
            for _, r in df.iterrows():
                try:
                    rows.append({
                        "date": str(r.iloc[0])[:10],
                        "bullish": float(r.iloc[1]) if r.iloc[1] else None,
                        "neutral": float(r.iloc[2]) if r.iloc[2] else None,
                        "bearish": float(r.iloc[3]) if r.iloc[3] else None,
                    })
                except Exception:
                    continue
        except Exception as e:
            log.error("Failed to parse AAII Excel: %s", e)
            return 1
    except Exception as e:
        log.error("Failed to parse AAII Excel with xlrd: %s", e)
        return 1

    if not rows:
        log.warning("No AAII rows parsed (non-fatal)")
        return 0

    conn = get_db_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for row in rows:
                if not row.get("date"):
                    continue
                cur.execute(
                    """INSERT INTO aaii_sentiment (date, bullish, neutral, bearish)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (date) DO UPDATE
                         SET bullish  = EXCLUDED.bullish,
                             neutral  = EXCLUDED.neutral,
                             bearish  = EXCLUDED.bearish""",
                    (row["date"], row["bullish"], row["neutral"], row["bearish"]),
                )
                inserted += 1
        conn.commit()
        log.info("AAII sentiment: upserted %d rows", inserted)
    finally:
        conn.close()

    return 0


def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run()


if __name__ == "__main__":
    sys.exit(main())
