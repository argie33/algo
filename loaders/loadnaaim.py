#!/usr/bin/env python3
"""NAAIM Exposure Index Loader — weekly institutional equity exposure data.

Scrapes current Excel URL from NAAIM website (they rename the file weekly).
Table: naaim (date, naaim_number_mean, bullish, bearish)

Run: python3 loaders/loadnaaim.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import io
import logging
import re
from datetime import date

import requests

from config.env_loader import load_env

log = logging.getLogger(__name__)

NAAIM_PAGE = "https://www.naaim.org/programs/naaim-exposure-index/"
NAAIM_BASE = "https://www.naaim.org"


def _discover_naaim_url() -> str:
    """Scrape NAAIM website to find current Excel filename."""
    resp = requests.get(NAAIM_PAGE, timeout=30,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; AlgoBot/1.0)"})
    resp.raise_for_status()
    html = resp.text
    # File format: USE_Data-since-Inception_YYYY-MM-DD.xlsx
    match = re.search(
        r'href=["\']([^"\']*USE_Data[^"\']*\.xlsx)["\']', html, re.IGNORECASE
    )
    if not match:
        raise ValueError("Could not find NAAIM Excel URL on page")
    url = match.group(1)
    if not url.startswith("http"):
        url = NAAIM_BASE + ("" if url.startswith("/") else "/") + url
    log.info("Discovered NAAIM URL: %s", url)
    return url


def _parse_xlsx(content: bytes) -> list:
    """Parse NAAIM Excel file. Returns list of dicts for insertion."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        ws = wb.active
    except Exception:
        # Fallback: try xlrd for older .xlsx
        import xlrd
        wb = xlrd.open_workbook(file_contents=content)
        ws = wb.sheet_by_index(0)
        return _parse_xlrd(ws)

    rows_out = []
    header_found = False
    col_map = {}
    for row in ws.iter_rows(values_only=True):
        if not header_found:
            # Find header row by looking for "Date" or "date"
            for i, cell in enumerate(row):
                if cell and str(cell).strip().lower() in ("date", "week ending"):
                    header_found = True
                    col_map["date"] = i
                elif cell and "mean" in str(cell).lower():
                    col_map["mean"] = i
                elif cell and "most bearish" in str(cell).lower():
                    col_map["bearish"] = i
                elif cell and "quart3" in str(cell).lower() or (cell and "75" in str(cell)):
                    col_map["bullish"] = i
            continue

        if not row or row[0] is None:
            continue

        try:
            # Parse date
            raw_date = row[col_map.get("date", 0)]
            if raw_date is None:
                continue
            if hasattr(raw_date, "date"):
                d = raw_date.date().isoformat()
            elif hasattr(raw_date, "isoformat"):
                d = raw_date.isoformat()[:10]
            else:
                from datetime import datetime
                try:
                    d = str(raw_date)[:10]
                    datetime.fromisoformat(d)
                except ValueError:
                    continue

            mean_idx = col_map.get("mean", 1)
            bearish_idx = col_map.get("bearish", 2)
            bullish_idx = col_map.get("bullish", 5)

            mean_val = row[mean_idx] if mean_idx < len(row) else None
            bearish_val = row[bearish_idx] if bearish_idx < len(row) else None
            bullish_val = row[bullish_idx] if bullish_idx < len(row) else None

            rows_out.append({
                "date": d,
                "naaim_number_mean": float(mean_val) if mean_val is not None else None,
                "bullish": float(bullish_val) if bullish_val is not None else None,
                "bearish": float(bearish_val) if bearish_val is not None else None,
            })
        except Exception as e:
            log.debug("Skipping NAAIM row: %s", e)

    return rows_out


def _parse_xlrd(ws) -> list:
    """Fallback xlrd parser."""
    rows_out = []
    header_row = None
    col_map = {}
    for rx in range(ws.nrows):
        row = ws.row_values(rx)
        if header_row is None:
            for i, cell in enumerate(row):
                cs = str(cell).strip().lower()
                if cs in ("date", "week ending"):
                    header_row = rx
                    col_map["date"] = i
                elif "mean" in cs:
                    col_map["mean"] = i
                elif "most bearish" in cs:
                    col_map["bearish"] = i
                elif "quart3" in cs or "75" in cs:
                    col_map["bullish"] = i
            continue
        if not row or row[0] == "":
            continue
        try:
            import xlrd as xlrd_mod
            from datetime import datetime
            raw = row[col_map.get("date", 0)]
            if isinstance(raw, float):
                dt = xlrd_mod.xldate_as_datetime(raw, ws.book.datemode)
                d = dt.date().isoformat()
            else:
                d = str(raw)[:10]
            rows_out.append({
                "date": d,
                "naaim_number_mean": float(row[col_map.get("mean", 1)]) if row[col_map.get("mean", 1)] != "" else None,
                "bullish": float(row[col_map.get("bullish", 5)]) if row[col_map.get("bullish", 5)] != "" else None,
                "bearish": float(row[col_map.get("bearish", 2)]) if row[col_map.get("bearish", 2)] != "" else None,
            })
        except Exception as e:
            log.debug("Skipping NAAIM xlrd row: %s", e)
    return rows_out


def run() -> int:
    from utils.db_connection import get_db_connection

    try:
        url = _discover_naaim_url()
    except Exception as e:
        log.error("Cannot find NAAIM URL: %s", e)
        return 1

    try:
        resp = requests.get(url, timeout=60,
                            headers={"User-Agent": "Mozilla/5.0 (compatible; AlgoBot/1.0)"})
        resp.raise_for_status()
        content = resp.content
    except Exception as e:
        log.error("Failed to download NAAIM Excel: %s", e)
        return 1

    rows = _parse_xlsx(content)
    if not rows:
        log.error("No NAAIM rows parsed from Excel")
        return 1

    conn = get_db_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for row in rows:
                if row["date"] is None:
                    continue
                cur.execute(
                    """INSERT INTO naaim (date, naaim_number_mean, bullish, bearish)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (date) DO UPDATE
                         SET naaim_number_mean = EXCLUDED.naaim_number_mean,
                             bullish = EXCLUDED.bullish,
                             bearish = EXCLUDED.bearish""",
                    (row["date"], row["naaim_number_mean"], row["bullish"], row["bearish"]),
                )
                inserted += 1
        conn.commit()
        log.info("NAAIM: upserted %d rows", inserted)
    finally:
        conn.close()

    return 0


def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run()


if __name__ == "__main__":
    sys.exit(main())
