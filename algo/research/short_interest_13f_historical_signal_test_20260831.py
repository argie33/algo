#!/usr/bin/env python3
"""Real historical-depth test of institutional ownership (13F) and short interest as composite
signals - built 2026-08-31 in direct response to user pushback that this session's earlier
"untestable for lack of historical depth" conclusion was based on the PRODUCTION LOADERS' latest-
only-cycle design, not the true depth of the underlying sources.

Live-verified before writing this script (not assumed):
- FINRAShortInterestFetcher.fetch_date(target_date) accepts an arbitrary historical settlement
  date and returns real data back to 2017-12-29 (bisected live: 2017-11-30 and earlier fail,
  2017-12-29 onward works) - ~8.7 years, not "~2 real months" as the production loader's own
  4-cycle-lookback `fetch_latest()` implied.
- SEC's own 13F data-sets page currently lists 10 quarterly bulk datasets (2024-01 through
  2026-03 filing windows) - 8 real historical quarters, not "1 row/symbol" as the production
  loader's single-latest-dataset `_discover_latest_13f_bulk_dataset()` implied.

This is pure research - does NOT write to any production table, does NOT modify any loader.
Reuses production loader internals (FINRAShortInterestFetcher, InstitutionalHoldings13FLoader's
_fetch_and_parse_13f_bulk/_crosswalk_to_tickers/_calculate_and_cache_ownership - the last one
despite its name only READS from DB, confirmed by inspection before use) and this project's own
established Fama-MacBeth methodology (algo/research/fama_macbeth_composite_weights.py's
build_pillar_proxy_records() for the 5 existing pillar-proxy controls, fama_macbeth_price_factors.py's
_fama_macbeth() regression helper convention).
"""

import logging
import re
import time
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from algo.infrastructure import MarketCalendar
from algo.research.fama_macbeth_composite_weights import build_pillar_proxy_records
from loaders.load_institutional_holdings_13f import SEC_13F_DATASETS_PAGE, InstitutionalHoldings13FLoader
from utils.db.context import DatabaseContext
from utils.finra_short_interest import FINRAShortInterestFetcher

logger = logging.getLogger(__name__)

PILLAR_COLS = ["growth_proxy", "value_proxy", "quality_proxy", "stability_proxy", "momentum_proxy"]
FINRA_REPORTING_LAG_DAYS = 21  # this loader's own docstring: "published ~2-3 weeks after settlement"


def _zwinsor(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def _fama_macbeth(
    records: list[tuple[pd.Timestamp, pd.DataFrame]], cols: list[str]
) -> dict[str, tuple[float, float, int]]:
    """Same convention as fama_macbeth_price_factors.py's _fama_macbeth: one cross-sectional OLS
    per month, average the coefficient time series. Returns {name: (mean_coef, t_stat, n_months)}."""
    coef_hist: dict[str, list[float]] = {c: [] for c in ["const", *cols]}
    for _month, frame in records:
        sub = frame.dropna(subset=[*cols, "fwd_ret"])
        if len(sub) < 30:
            continue
        x = np.column_stack([np.ones(len(sub))] + [sub[c].values for c in cols])
        y = sub["fwd_ret"].values
        coefs, *_ = np.linalg.lstsq(x, y, rcond=None)
        for j, name in enumerate(["const", *cols]):
            coef_hist[name].append(coefs[j])
    results = {}
    for name, series in coef_hist.items():
        arr = np.array(series)
        if len(arr) < 3:
            results[name] = (float("nan"), float("nan"), len(arr))
            continue
        mean = arr.mean()
        se = arr.std(ddof=1) / np.sqrt(len(arr))
        results[name] = (mean, mean / se if se > 0 else float("nan"), len(arr))
    return results


def _half_split(records: list[tuple[pd.Timestamp, pd.DataFrame]]) -> tuple[list[Any], list[Any]]:
    mid = len(records) // 2
    return records[:mid], records[mid:]


# ─── PART A: short interest ────────────────────────────────────────────────


def find_earliest_finra_date() -> date:
    """Already bisected live in the parent session: 2017-11-30 and earlier fail, 2017-12-29
    works. Re-verify the exact boundary once here (cheap, 2 calls) rather than trust the parent's
    interactive-shell finding blindly - this script needs to be self-contained evidence."""
    f = FINRAShortInterestFetcher()
    assert len(f.fetch_date(date(2017, 12, 29))) > 0, "expected earliest-known-good FINRA date to still work"
    assert len(f.fetch_date(date(2017, 11, 30))) == 0, "expected earliest-known-bad FINRA date to still fail"
    return date(2017, 12, 29)


def monthly_settlement_dates(start: date, end: date) -> list[date]:
    """Last-trading-day-of-month settlement dates from start's month through end's month,
    adjusted via MarketCalendar (matches this project's own 'date math via MarketCalendar only'
    rule) - NOT hand-rolled weekend arithmetic."""
    dates = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        last_day = (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)) - timedelta(days=1)
        adj = MarketCalendar.get_previous_trading_day(last_day)
        if adj is not None:
            dates.append(adj)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return sorted(set(dates))


def fetch_finra_panel(dates: list[date]) -> dict[date, dict[str, dict[str, Any]]]:
    f = FINRAShortInterestFetcher()
    panel: dict[date, dict[str, dict[str, Any]]] = {}
    skipped = []
    for i, d in enumerate(dates):
        for attempt in range(3):
            try:
                data = f.fetch_date(d)
                panel[d] = data
                break
            except Exception as e:
                if attempt == 2:
                    skipped.append((d, str(e)[:150]))
                    logger.warning(f"[FINRA] {d} failed after 3 attempts: {e}")
                else:
                    time.sleep(2.0 * (attempt + 1))
        if (i + 1) % 10 == 0:
            logger.info(f"[FINRA] fetched {i + 1}/{len(dates)} dates")
    if skipped:
        logger.warning(f"[FINRA] {len(skipped)} dates skipped entirely: {skipped}")
    return panel


def fetch_shares_outstanding_pit() -> pd.DataFrame:
    """Point-in-time shares outstanding from annual_income_statement (same source/convention
    the goal2 raw-input script already uses), NOT the production short-interest loader's single
    current-shares-outstanding value - a decade of history needs point-in-time shares, not
    today's share count applied retroactively (a real look-ahead bias the production loader
    correctly doesn't care about for live scoring, but this backtest must)."""
    sql = """
        SELECT symbol, fiscal_year,
               COALESCE(shares_outstanding_diluted, shares_outstanding_basic, shares_outstanding_dei) AS shares
        FROM annual_income_statement
        WHERE fiscal_year BETWEEN 2010 AND 2026
          AND COALESCE(shares_outstanding_diluted, shares_outstanding_basic, shares_outstanding_dei) > 0
        ORDER BY symbol, fiscal_year
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "fiscal_year", "shares"])
    df["shares"] = df["shares"].astype(
        float
    )  # DB returns Decimal - float before any arithmetic (feedback_psycopg2_decimal_arithmetic)
    df["known_date"] = pd.to_datetime(df["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(days=90)
    return df


def build_short_interest_frame(
    finra_panel: dict[date, dict[str, dict[str, Any]]], shares_pit: pd.DataFrame
) -> pd.DataFrame:
    """One row per (settlement_date, symbol): short_pct, short_pct_change_1m. Point-in-time
    shares outstanding via as-of merge (most recent known_date <= settlement_date + reporting lag)."""
    shares_sorted = shares_pit.sort_values("known_date")
    rows = []
    for d in sorted(finra_panel):
        data = finra_panel[d]
        frame = pd.DataFrame(
            [{"symbol": sym, "short_shares": v.get("short_shares")} for sym, v in data.items() if v.get("short_shares")]
        )
        frame["settlement_date"] = pd.Timestamp(d)
        rows.append(frame)
    if not rows:
        return pd.DataFrame()
    all_rows = pd.concat(rows, ignore_index=True)

    # as-of merge shares outstanding (known as of settlement_date + FINRA reporting lag, so we're
    # using shares data that would genuinely have been available, not a future filing)
    all_rows = all_rows.sort_values("settlement_date")
    merged_parts = []
    for sym, g in all_rows.groupby("symbol"):
        sh = shares_sorted[shares_sorted["symbol"] == sym]
        if sh.empty:
            continue
        g = g.sort_values("settlement_date")
        as_of_cutoff = g["settlement_date"] + pd.Timedelta(days=FINRA_REPORTING_LAG_DAYS)
        merged = pd.merge_asof(
            g.assign(_cutoff=as_of_cutoff).sort_values("_cutoff"),
            sh[["known_date", "shares"]].sort_values("known_date"),
            left_on="_cutoff",
            right_on="known_date",
            direction="backward",
        )
        merged_parts.append(merged)
    if not merged_parts:
        return pd.DataFrame()
    out = pd.concat(merged_parts, ignore_index=True)
    out["short_pct"] = np.where(out["shares"] > 0, 100.0 * out["short_shares"] / out["shares"], np.nan)
    out = out.dropna(subset=["short_pct"])
    out = out[
        (out["short_pct"] >= 0) & (out["short_pct"] <= 100)
    ]  # sanity bound, not a silent clip - drop, don't clamp
    out = out.sort_values(["symbol", "settlement_date"])
    out["short_pct_change_1m"] = out.groupby("symbol")["short_pct"].diff(1)
    out["settlement_date"] = out["settlement_date"] + pd.Timedelta(days=FINRA_REPORTING_LAG_DAYS)
    return out[["symbol", "settlement_date", "short_pct", "short_pct_change_1m"]]


def run_part_a() -> None:
    print("\n" + "=" * 78)
    print("PART A: short interest (FINRA) - real historical depth test")
    print("=" * 78)
    earliest = find_earliest_finra_date()
    print(f"Earliest working FINRA settlement date, re-verified live: {earliest}")

    today = datetime.now().date()
    dates = monthly_settlement_dates(earliest, today)
    print(f"Building monthly panel: {len(dates)} settlement dates, {dates[0]} to {dates[-1]}")

    finra_panel = fetch_finra_panel(dates)
    print(f"Fetched {len(finra_panel)}/{len(dates)} dates successfully")

    shares_pit = fetch_shares_outstanding_pit()
    print(f"Point-in-time shares-outstanding panel: {len(shares_pit)} symbol-fiscal-year rows")

    si_frame = build_short_interest_frame(finra_panel, shares_pit)
    print(f"Short-interest frame: {len(si_frame)} symbol-settlement-date rows")
    print("short_pct distribution:", si_frame["short_pct"].describe().to_dict())

    print("\nBuilding 5-pillar-proxy panel (reusing fama_macbeth_composite_weights.build_pillar_proxy_records)...")
    _partial, _complete, records_raw = build_pillar_proxy_records(
        start_date="2015-01-01", end_date=today.isoformat(), min_cross_section=300
    )
    print(f"Pillar-proxy panel: {len(records_raw)} months, {records_raw[0][0]} to {records_raw[-1][0]}")

    # merge short interest onto each pillar-proxy month (as-of: most recent known short-interest
    # obs <= that month's date, within a 45-day staleness window - stale reads become NaN, not a
    # fabricated carry-forward)
    si_sorted = si_frame.sort_values("settlement_date")
    combined_records = []
    for month, frame in records_raw:
        cutoff = pd.Timestamp(month)
        window = si_sorted[si_sorted["settlement_date"] <= cutoff]
        if window.empty:
            continue
        latest_per_symbol = window.sort_values("settlement_date").groupby("symbol").tail(1)
        latest_per_symbol = latest_per_symbol.set_index("symbol")
        staleness = cutoff - latest_per_symbol["settlement_date"]
        latest_per_symbol = latest_per_symbol[staleness <= pd.Timedelta(days=45)]
        if latest_per_symbol.empty:
            continue
        merged = frame.join(latest_per_symbol[["short_pct", "short_pct_change_1m"]], how="inner")
        if len(merged) < 30:
            continue
        merged["short_pct_z"] = _zwinsor(merged["short_pct"])
        merged["short_pct_change_1m_z"] = _zwinsor(merged["short_pct_change_1m"].fillna(0.0))
        combined_records.append((month, merged))

    print(f"\nUsable merged months (pillar proxies + short interest, >=30 symbols): {len(combined_records)}")
    if len(combined_records) < 12:
        print(
            "TOO FEW MONTHS TO RUN A MEANINGFUL FAMA-MACBETH TEST - stopping Part A here, reporting as INCONCLUSIVE, not null."
        )
        return

    full = combined_records
    era1, era2 = _half_split(full)

    for label, cols in [
        ("short_pct LEVEL, univariate", ["short_pct_z"]),
        ("short_pct LEVEL, multivariate (+5 pillars)", ["short_pct_z", *PILLAR_COLS]),
        ("short_pct CHANGE (1mo), univariate", ["short_pct_change_1m_z"]),
        ("short_pct CHANGE (1mo), multivariate (+5 pillars)", ["short_pct_change_1m_z", *PILLAR_COLS]),
    ]:
        print(f"\n--- {label} ---")
        for era_name, era_records in [("FULL", full), ("ERA1", era1), ("ERA2", era2)]:
            res = _fama_macbeth(era_records, cols)
            key = cols[0]
            mean, t, n = res[key]
            print(f"  {era_name:5s} n_months={n:4d}  mean_coef={mean:10.6f}  t={t:7.3f}")


# ─── PART B: 13F institutional ownership ───────────────────────────────────


def discover_all_13f_datasets() -> list[tuple[str, date]]:
    req = urllib.request.Request(SEC_13F_DATASETS_PAGE, headers={"User-Agent": "algo-research contact@example.com"})
    # SEC_13F_DATASETS_PAGE is a hardcoded "https://www.sec.gov/..." literal (see its
    # definition in loaders/load_institutional_holdings_13f.py) - not user/request-controlled,
    # so bandit's file://-scheme-confusion warning doesn't apply here.
    html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="ignore")  # nosec B310
    pattern = re.compile(
        r'href="(/files/[a-z]+/data/form-13f-data-sets/(\d{2}[a-z]{3}\d{4})-(\d{2}[a-z]{3}\d{4})_form13f\.zip)"',
        re.IGNORECASE,
    )
    out = []
    for path, _start_str, end_str in pattern.findall(html):
        period_end = datetime.strptime(end_str, "%d%b%Y").date()
        out.append((f"https://www.sec.gov{path}", period_end))
    return sorted(out, key=lambda t: t[1])


def run_part_b() -> None:
    print("\n" + "=" * 78)
    print("PART B: 13F institutional ownership - real historical depth test")
    print("=" * 78)
    datasets = discover_all_13f_datasets()
    print(f"Discovered {len(datasets)} historical quarterly 13F bulk datasets: {[d.isoformat() for _u, d in datasets]}")
    if len(datasets) < 4:
        print("Too few historical datasets available - reporting INCONCLUSIVE, not null.")
        return

    loader = InstitutionalHoldings13FLoader()
    tracked_cusips = loader._get_known_tracked_cusips()
    print(f"Tracked CUSIPs from existing crosswalk cache: {len(tracked_cusips)}")

    quarterly_ownership: dict[date, pd.DataFrame] = {}
    for url, period_end in datasets:
        print(f"\nFetching {url} (period end {period_end})...")
        try:
            holdings_by_cusip, manager_holdings_by_cusip = loader._fetch_and_parse_13f_bulk(url, tracked_cusips)
            holdings_by_ticker, _manager_by_ticker = loader._crosswalk_to_tickers(
                holdings_by_cusip, manager_holdings_by_cusip
            )
            print(f"  {len(holdings_by_cusip)} CUSIPs -> {len(holdings_by_ticker)} tickers resolved")
            if not holdings_by_ticker:
                continue
            records = loader._calculate_and_cache_ownership(holdings_by_ticker, period_end, {})
            df = pd.DataFrame(records)
            if "institutional_ownership_pct" not in df.columns or "symbol" not in df.columns:
                print(f"  unexpected record shape, columns={list(df.columns)}, skipping this quarter")
                continue
            df = df[["symbol", "institutional_ownership_pct"]].dropna()
            df = df[(df["institutional_ownership_pct"] >= 0) & (df["institutional_ownership_pct"] <= 100)]
            quarterly_ownership[period_end] = df.set_index("symbol")["institutional_ownership_pct"].astype(float)
            print(f"  {len(df)} symbols with real ownership_pct this quarter")
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {str(e)[:200]}")

    print(f"\nQuarters with usable ownership data: {len(quarterly_ownership)}")
    if len(quarterly_ownership) < 4:
        print("TOO FEW QUARTERS TO RUN A MEANINGFUL TEST - stopping Part B here, reporting as INCONCLUSIVE, not null.")
        return

    print("\nBuilding 5-pillar-proxy panel (reusing same call, cached from Part A if run in-process)...")
    today = datetime.now().date()
    _partial, _complete, records_raw = build_pillar_proxy_records(
        start_date="2015-01-01", end_date=today.isoformat(), min_cross_section=300
    )
    pillar_by_month = {pd.Timestamp(m).to_period("M"): frame for m, frame in records_raw}

    quarters_sorted = sorted(quarterly_ownership)
    combined_records = []
    prior_own: pd.Series | None = None
    for q_end in quarters_sorted:
        own = quarterly_ownership[q_end]
        own_change = (own - prior_own).dropna() if prior_own is not None else pd.Series(dtype=float)
        prior_own = own
        # 45-day 13F filing deadline -> known ~45 days after period end
        known = pd.Timestamp(q_end) + pd.Timedelta(days=45)
        period = known.to_period("M")
        if period not in pillar_by_month:
            continue
        frame = pillar_by_month[period]
        merged = frame.join(own.rename("own_pct"), how="inner")
        if not own_change.empty:
            merged = merged.join(own_change.rename("own_pct_change"), how="left")
        else:
            merged["own_pct_change"] = np.nan
        if len(merged) < 30:
            continue
        merged["own_pct_z"] = _zwinsor(merged["own_pct"])
        merged["own_pct_change_z"] = _zwinsor(merged["own_pct_change"].fillna(0.0))
        combined_records.append((known, merged))

    print(
        f"Usable merged quarter-months: {len(combined_records)} (this project's usual bar is ~110+ months - treat this as a preliminary read, not a definitive verdict)"
    )
    if len(combined_records) < 4:
        print("TOO FEW MERGED QUARTERS - INCONCLUSIVE.")
        return

    for label, cols in [
        ("ownership LEVEL, univariate", ["own_pct_z"]),
        ("ownership LEVEL, multivariate (+5 pillars)", ["own_pct_z", *PILLAR_COLS]),
        ("ownership CHANGE (QoQ), univariate", ["own_pct_change_z"]),
        ("ownership CHANGE (QoQ), multivariate (+5 pillars)", ["own_pct_change_z", *PILLAR_COLS]),
    ]:
        print(f"\n--- {label} (n={len(combined_records)} quarter-months, SMALL SAMPLE) ---")
        res = _fama_macbeth(combined_records, cols)
        key = cols[0]
        mean, t, n = res[key]
        print(
            f"  n_months={n:2d}  mean_coef={mean:10.6f}  t={t:7.3f}  (no half-split - too few quarters to split meaningfully)"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_part_a()
    run_part_b()
    print("\nDONE.")
