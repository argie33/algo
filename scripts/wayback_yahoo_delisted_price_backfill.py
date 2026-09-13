#!/usr/bin/env python3
"""Free, no-daily-quota backfill of historical prices for delisted/bankrupt symbols, scraped
from the Wayback Machine's archived captures of the (now dead) Yahoo Finance historical-price
endpoints - a companion to scripts/tiingo_delisted_price_backfill.py for the survivorship-bias
gap that Tiingo's free tier structurally cannot reach.

Added 2026-09-13. Tiingo's free tier was verified to carry real delisted-company history for
~2023-era failures (SIVB, SBNY) but confirmed to NOT reach Lehman/Bear Stearns/WaMu/Enron/
WorldCom (2001-2008 era) - and a live test of EOD Historical Data's free tier the same session
confirmed the same structural gap for a different reason (1-year rolling lookback on ANY
ticker, regardless of budget). Neither vendor's free tier can reach multi-decade-old delisted
history at all.

What can: web.archive.org has real point-in-time crawls of Yahoo Finance's old CSV-download
endpoint (ichart.finance.yahoo.com/table.csv, and its predecessor chart.yahoo.com/table.csv)
and its "Historical Prices" HTML page (finance.yahoo.com/q/hp), going back to ~1999, INCLUDING
captures taken during/immediately after several of these companies' actual collapses - e.g. a
real 2008-12-18 capture of Lehman's post-bankruptcy pink-sheet ticker (LEHMQ.PK) showing
$0.03-0.04/share trades, confirmed live this session by fetching it directly. Yahoo's own
archived pages self-document ticker-change chains (e.g. a 2008-09-26 capture of the LEH page
literally says "'LEH' is no longer valid. It has changed to LEHMQ.PK") - this script follows
that chain automatically instead of requiring a hand-maintained mapping table.

No API key, no daily quota - the only constraint is being a good citizen of a free public
archive, hence the flat inter-request sleep (mirrors tiingo_delisted_price_backfill.py's own
"slow drip by design" posture, budget is about politeness here, not a vendor cap).

DELIBERATELY sources candidates from the existing `stock_symbols WHERE active = false`
population by default (same anti-"survivor-of-fame bias" reasoning as
tiingo_delisted_price_backfill.py - a curated famous-names-only list would just trade one bias
for another). Migration 1287 separately seeded stock_symbols + delisting_events rows for the
handful of pre-Tiingo-era mega-failures (LEH, BSC, WAMUQ, ENE, WCOM, SHLD, JCP, CS, TOY, FRC)
that were confirmed completely absent from stock_symbols before this session - not just
missing prices, missing as symbols at all - so they now surface as candidates through the same
unbiased selection query rather than needing a separate code path.

Usage:
    python scripts/wayback_yahoo_delisted_price_backfill.py                    # up to 15 symbols
    python scripts/wayback_yahoo_delisted_price_backfill.py --budget 5
    python scripts/wayback_yahoo_delisted_price_backfill.py --symbols LEH,BSC,WAMUQ,ENE,WCOM
    python scripts/wayback_yahoo_delisted_price_backfill.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CDX_API_URL = "http://web.archive.org/cdx/search/cdx"
WAYBACK_RAW_URL = "https://web.archive.org/web/{timestamp}id_/{original}"
USER_AGENT = "algo-trading argeropolos@gmail.com (Wayback Machine historical price backfill, low-volume/good-citizen)"
DEFAULT_BUDGET = 15
REQUEST_TIMEOUT_SEC = 30
# Be polite to a free public archive - this is a slow drip by design, not a race to spend budget.
INTER_REQUEST_SLEEP_SEC = 1.5

# Domains that historically served the CSV download / HTML historical-prices endpoints, oldest
# first - Yahoo moved this around several times between 1999 and its 2017 API shutdown.
CSV_DOMAINS = [
    "ichart.finance.yahoo.com/table.csv",
    "chart.yahoo.com/table.csv",
    "table.finance.yahoo.com/table.csv",
]
HP_PAGE_DOMAIN = "finance.yahoo.com/q/hp"

_MONTH_ABBR = {
    m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
}


def _select_candidate_symbols(cur: Any, limit: int, explicit_symbols: list[str] | None) -> list[str]:
    if explicit_symbols:
        return explicit_symbols

    cur.execute(
        """
        SELECT s.symbol
        FROM stock_symbols s
        LEFT JOIN wayback_backfill_status w ON w.symbol = s.symbol
        WHERE s.active = FALSE
          AND w.symbol IS NULL
        ORDER BY
            (EXISTS (SELECT 1 FROM delisting_events de WHERE de.symbol = s.symbol)) DESC,
            s.symbol
        LIMIT %s
        """,
        (limit,),
    )
    return [row[0] for row in cur.fetchall()]


def _cdx_session() -> Any:
    import requests

    from loaders.timeout_config import configure_requests_session

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    configure_requests_session(session, timeout=(10.0, REQUEST_TIMEOUT_SEC))
    return session


def _cdx_search(session: Any, url_prefix: str, symbol: str) -> list[dict[str, str]]:
    """Query the Wayback CDX API for captures of url_prefix whose query string contains
    s=<symbol> (case-insensitive, exact param match - CDX canonicalizes/sorts query params
    alphabetically in the urlkey, so a plain '&' or end-of-string boundary check is enough to
    avoid accidental substring collisions, e.g. LEH matching LEHMQ)."""
    resp = session.get(
        CDX_API_URL,
        params={
            "url": url_prefix,
            "matchType": "prefix",
            # Allows an optional OTC/pink-sheet suffix Yahoo appended to the bare symbol after
            # a bankruptcy/reorg (e.g. WAMUQ -> WAMUQ.PK) - confirmed live this session that
            # the bare-symbol search finds nothing for WaMu at all, only ".pk" does - while
            # still requiring a real boundary (& or end-of-string) after that suffix so e.g.
            # "leh" doesn't accidentally match a real different symbol like "lehjq".
            # Boundary is '&', end-of-string, OR '+' - some real archived URLs append literal
            # "+Historical+Prices" after the symbol (a stray query-string artifact of the page's
            # own search box), confirmed live this session (MF Global's only surviving capture,
            # 463 real price-table cells, uses exactly this shape) - requiring a hard stop would
            # silently miss it.
            "filter": f"urlkey:.*[?&]s={symbol.lower()}(\\.[a-z]{{1,3}})?(&|$|\\+).*",
            "output": "json",
            "limit": 100,
        },
        timeout=REQUEST_TIMEOUT_SEC,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data or len(data) < 2:
        return []
    header = data[0]
    return [dict(zip(header, row, strict=True)) for row in data[1:]]


def _fetch_raw_capture(session: Any, capture: dict[str, str]) -> str:
    raw_url = WAYBACK_RAW_URL.format(timestamp=capture["timestamp"], original=capture["original"])
    resp = session.get(raw_url, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    return str(resp.text)


def _requested_year_span(capture: dict[str, str]) -> int:
    """Yahoo's legacy date-range params encode start/end year as c=YYYY and f=YYYY (0-indexed
    month in a/d, ignored here). A capture requesting a 15-year span carries far more history
    than one requesting a single quarter, independent of when the capture itself was taken."""
    m = re.search(r"[?&]c=(\d{4})", capture["original"])
    n = re.search(r"[?&]f=(\d{4})", capture["original"])
    if not m or not n:
        return 0
    return abs(int(n.group(1)) - int(m.group(1)))


def _by_recency(captures: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sorts status=200 captures by crawl timestamp, most recent first."""
    ok = [c for c in captures if c.get("statuscode") == "200"]
    return sorted(ok, key=lambda c: c["timestamp"], reverse=True)


def _select_capture_candidates(captures: list[dict[str, str]], want: int = 3) -> list[dict[str, str]]:
    """Picks a small, diverse set of captures to actually fetch: the single widest requested
    date-range (catches deep pre-delisting history) plus the most recent crawl timestamps
    (catches data closest to the actual delisting/collapse date, which a wide-but-old capture
    may predate entirely) - complementary failure modes, so both need representation rather
    than picking by only one axis."""
    ok = [c for c in captures if c.get("statuscode") == "200"]
    if not ok:
        return []
    by_recency = sorted(ok, key=lambda c: c["timestamp"], reverse=True)
    widest = max(ok, key=_requested_year_span)

    selected: list[dict[str, str]] = [widest]
    for c in by_recency:
        if len(selected) >= want:
            break
        if c["timestamp"] not in [s["timestamp"] for s in selected]:
            selected.append(c)
    return selected


def _detect_ticker_change(html_or_csv: str) -> str | None:
    m = re.search(r"is no longer valid\. It has changed to <a href=\"[^\"]*\"><b>([A-Z0-9.\-]+)</b>", html_or_csv)
    return m.group(1) if m else None


def _parse_csv(text: str) -> list[dict[str, Any]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].lower().startswith("date"):
        return []
    rows = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        date = _parse_date_token(parts[0])
        if date is None:
            continue
        try:
            rows.append(
                {
                    "date": date,
                    "open": _to_float(parts[1]),
                    "high": _to_float(parts[2]),
                    "low": _to_float(parts[3]),
                    "close": _to_float(parts[4]),
                    "volume": _to_int(parts[5]),
                    "adj_close": _to_float(parts[6]) if len(parts) > 6 else _to_float(parts[4]),
                }
            )
        except ValueError:
            continue
    return rows


def _parse_hp_html_table(html: str) -> list[dict[str, Any]]:
    """Parses the legacy Yahoo 'yfnc_tabledata1' historical-prices table markup: one <tr> per
    row, 7 <td class="yfnc_tabledata1"> cells (Date, Open, High, Low, Close, Volume, Adj Close)."""
    rows = []
    for row_html in re.findall(r"<tr>\s*(<td class=\"yfnc_tabledata1\".*?)</tr>", html):
        cells = re.findall(r'<td class="yfnc_tabledata1"[^>]*>([^<]*)</td>', row_html)
        if len(cells) != 7:
            continue
        date = _parse_date_token(cells[0])
        if date is None:
            continue
        try:
            rows.append(
                {
                    "date": date,
                    "open": _to_float(cells[1]),
                    "high": _to_float(cells[2]),
                    "low": _to_float(cells[3]),
                    "close": _to_float(cells[4]),
                    "volume": _to_int(cells[5]),
                    "adj_close": _to_float(cells[6]),
                }
            )
        except ValueError:
            continue
    return rows


def _parse_date_token(token: str) -> str | None:
    token = token.strip()
    # CSV format: "18-Nov-05" or "2005-11-18"; older HTML table format: "17-Dec-08"
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{2,4})$", token)
    if m:
        day, mon_abbr, year = m.groups()
        month = _MONTH_ABBR.get(mon_abbr.title())
        if not month:
            return None
        year_i = int(year)
        if year_i < 100:
            year_i += 1900 if year_i >= 70 else 2000
        return f"{year_i:04d}-{month:02d}-{int(day):02d}"
    # Newer (~2010+) HTML table format: "Nov 4, 2011" - confirmed live this session on MF
    # Global's post-bankruptcy pink-sheet page, a later Yahoo layout revision than the
    # "17-Dec-08" style seen on Lehman's 2008 captures.
    m = re.match(r"^([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})$", token)
    if m:
        mon_abbr, day, year = m.groups()
        month = _MONTH_ABBR.get(mon_abbr.title())
        if not month:
            return None
        return f"{int(year):04d}-{month:02d}-{int(day):02d}"
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", token)
    if m:
        return token
    return None


def _to_float(token: str) -> float | None:
    token = token.strip().replace(",", "")
    if not token or token in ("-", "N/A"):
        return None
    return float(token)


def _to_int(token: str) -> int | None:
    token = token.strip().replace(",", "")
    if not token or token in ("-", "N/A"):
        return None
    return int(float(token))


_MAX_CHAIN_HOPS = 3


def _discover_ticker_chain(session: Any, symbol: str) -> tuple[list[str], list[str]]:
    """Finds every ticker a symbol changed to over time, e.g. LEH -> LEHMQ.PK.

    Once a symbol changes, EVERY capture from then on repeats the same "no longer valid"
    notice - so checking just the single most-recent HP-page capture is enough to detect a
    change, no need to scan every capture. Cheap by design: at most 1 fetch per hop, since
    this only needs to happen once per symbol per script run (chain result isn't cached
    across runs, but wayback_backfill_status prevents re-attempting an already-resolved
    symbol at all)."""
    chain = [symbol]
    notes: list[str] = []

    for _ in range(_MAX_CHAIN_HOPS):
        current = chain[-1]
        captures = _by_recency(_cdx_search(session, HP_PAGE_DOMAIN, current))
        time.sleep(INTER_REQUEST_SLEEP_SEC)
        if not captures:
            break
        html = _fetch_raw_capture(session, captures[0])
        time.sleep(INTER_REQUEST_SLEEP_SEC)
        change = _detect_ticker_change(html)
        if not change or change.upper() in [s.upper() for s in chain]:
            break
        chain.append(change)
        notes.append(f"{current} -> {change}")

    return chain, notes


def _fetch_prices_for_one_symbol(session: Any, symbol: str) -> list[dict[str, Any]]:
    """Tries CSV captures first (cleaner to parse, exists across 3 historical domains, and
    each capture returns a full date-range series in one fetch), falling back to HTML
    historical-prices-page table parsing only if no CSV capture is archived for this exact
    symbol.

    Merges rows across multiple candidate captures per domain rather than stopping at the
    first one with any data - a widest-date-range capture and a most-recent-timestamp capture
    cover complementary, often non-overlapping slices (deep pre-delisting history vs. data
    closest to the actual collapse/delisting date), and taking only one systematically misses
    the other."""
    # Yahoo's CSV endpoint moved domains over the years (chart.yahoo.com ~1999-2002,
    # ichart.finance.yahoo.com ~2002-2010s) - a single symbol's full history can be split
    # across all three, so every domain is checked and merged rather than stopping at the
    # first that returns anything.
    all_rows: list[dict[str, Any]] = []
    for domain in CSV_DOMAINS:
        candidates = _select_capture_candidates(_cdx_search(session, domain, symbol))
        time.sleep(INTER_REQUEST_SLEEP_SEC)
        for capture in candidates:
            text = _fetch_raw_capture(session, capture)
            time.sleep(INTER_REQUEST_SLEEP_SEC)
            all_rows.extend(_parse_csv(text))

    if all_rows:
        return all_rows

    candidates = _select_capture_candidates(_cdx_search(session, HP_PAGE_DOMAIN, symbol), want=5)
    time.sleep(INTER_REQUEST_SLEEP_SEC)
    for capture in candidates:
        html = _fetch_raw_capture(session, capture)
        time.sleep(INTER_REQUEST_SLEEP_SEC)
        all_rows.extend(_parse_hp_html_table(html))
    return all_rows


def _resolve_symbol_prices(session: Any, symbol: str) -> tuple[list[dict[str, Any]], str | None, str]:
    """Returns (price_rows, resolved_ticker_or_None, detail_message).

    First discovers the full ticker-change chain (e.g. LEH -> LEHMQ.PK after Lehman's 2008
    bankruptcy), then fetches price data for EVERY symbol in that chain and merges the
    results - the pre-change and post-change tickers each carry a different, non-overlapping
    slice of the company's real trading history, and only fetching one half would silently
    drop exactly the terminal-collapse data this backfill exists to recover."""
    chain, chain_notes = _discover_ticker_chain(session, symbol)
    resolved_ticker = chain[-1] if len(chain) > 1 else None

    all_rows: list[dict[str, Any]] = []
    for current_symbol in chain:
        all_rows.extend(_fetch_prices_for_one_symbol(session, current_symbol))

    # De-dupe by date, keep the row from the capture with the most complete data (has volume).
    by_date: dict[str, dict[str, Any]] = {}
    for row in all_rows:
        existing = by_date.get(row["date"])
        if existing is None or (existing.get("volume") is None and row.get("volume") is not None):
            by_date[row["date"]] = row

    detail = "; ".join(chain_notes) if chain_notes else "no ticker-change detected"
    return list(by_date.values()), resolved_ticker, detail


def _upsert_price_rows(cur: Any, symbol: str, rows: list[dict[str, Any]]) -> int:
    price_rows = [
        (
            symbol,
            row["date"],
            row.get("open"),
            row.get("high"),
            row.get("low"),
            row.get("close"),
            row.get("adj_close"),
            row.get("volume"),
            "wayback_yahoo",
        )
        for row in rows
        if row.get("close") is not None
    ]
    if not price_rows:
        return 0

    import psycopg2.extras

    inserted = psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, data_source)
        VALUES %s
        ON CONFLICT (symbol, date) DO NOTHING
        RETURNING symbol
        """,
        price_rows,
        fetch=True,
    )
    return len(inserted)


def _record_status(
    cur: Any, symbol: str, status: str, rows_inserted: int, resolved_ticker: str | None, detail: str
) -> None:
    cur.execute(
        """
        INSERT INTO wayback_backfill_status (symbol, status, rows_inserted, resolved_ticker, last_attempt_at, detail)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
        ON CONFLICT (symbol) DO UPDATE SET
            status = EXCLUDED.status,
            rows_inserted = EXCLUDED.rows_inserted,
            resolved_ticker = EXCLUDED.resolved_ticker,
            last_attempt_at = EXCLUDED.last_attempt_at,
            detail = EXCLUDED.detail
        """,
        (symbol, status, rows_inserted, resolved_ticker, detail[:500]),
    )


def run(budget: int, explicit_symbols: list[str] | None, dry_run: bool) -> dict[str, Any]:
    from utils.db.context import DatabaseContext

    mode = "read" if dry_run else "write"
    summary: dict[str, Any] = {"attempted": 0, "backfilled": 0, "no_data": 0, "errors": 0, "rows_inserted": 0}
    session = _cdx_session()

    with DatabaseContext(mode) as cur:
        symbols = _select_candidate_symbols(cur, budget, explicit_symbols)
        if not symbols:
            logger.info("No unattempted delisted/inactive symbols left to try - nothing to do")
            return summary

        logger.info(f"Attempting {len(symbols)} symbol(s) this run (budget={budget}, dry_run={dry_run})")

        for symbol in symbols:
            summary["attempted"] += 1
            try:
                rows, resolved_ticker, detail = _resolve_symbol_prices(session, symbol)
            except Exception as e:
                logger.error(f"{symbol}: fetch/parse failed: {e}")
                summary["errors"] += 1
                if not dry_run:
                    _record_status(cur, symbol, "error", 0, None, str(e))
                continue

            if not rows:
                logger.info(f"{symbol}: no usable price rows found in any Wayback capture ({detail})")
                summary["no_data"] += 1
                if not dry_run:
                    _record_status(cur, symbol, "no_data_at_vendor", 0, resolved_ticker, detail)
                continue

            if dry_run:
                logger.info(f"{symbol}: would insert up to {len(rows)} price rows (dry-run, not writing; {detail})")
                summary["backfilled"] += 1
                continue

            inserted = _upsert_price_rows(cur, symbol, rows)
            _record_status(cur, symbol, "backfilled", inserted, resolved_ticker, f"{len(rows)} rows parsed; {detail}")
            logger.info(f"{symbol}: inserted {inserted} new price_daily row(s) ({len(rows)} parsed; {detail})")
            summary["backfilled"] += 1
            summary["rows_inserted"] += inserted

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="Max symbols to attempt this run")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols to force-attempt")
    parser.add_argument("--dry-run", action="store_true", help="Print only, don't write to the database")
    args = parser.parse_args()

    explicit_symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    summary = run(args.budget, explicit_symbols, args.dry_run)
    logger.info(f"Done: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
