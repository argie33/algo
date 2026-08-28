#!/usr/bin/env python3
"""
Tests 4 quarterly earnings-quality/growth candidates that have real computed data in
growth_metrics (populated by loaders/load_value_quality_growth_metrics.py's
_compute_quarterly_metrics(), 27%-90% coverage) but have NEVER been isolated-FM-tested for
scoring inclusion in Growth (or Quality) - built 2026-08-27 (goal-mode data-coverage session,
user question: "we should have tons more growth metrics... I see some missing from growth").

Prior state (confirmed via code/memory audit before building this): these 4 fields were cut from
the StockScoreAccordion.jsx DISPLAY layer on 2026-08-16 ("SECOND PASS: cut every unweighted
'Tracked (Not Scored)' field... per user request") alongside 2 analyst-estimate-dependent
siblings (earnings_surprise_avg, earnings_beat_rate) - a UX/scope decision, not an empirical
rejection. A later memory note ("MEMORY.md scoresdashboard...") describes them as "reference-only"
without citing a significance test. One field (quarterly_growth_momentum) had a memory claim it
"has no computation logic anywhere... genuinely, permanently dead" - checked directly against
loaders/load_value_quality_growth_metrics.py's _compute_quarterly_metrics() (lines ~1441-1580)
and found that claim FALSE: it's computed from quarterly_income_statement (revenue QoQ growth,
trailing 4 quarters), 79.5% live coverage - a stale/incorrect memory entry, not a dead field.

earnings_surprise_avg/earnings_beat_rate are NOT included here - confirmed (same file, ~line
1591-1605) they require analyst_earnings_estimates, which per
growth_missing_metrics_swept_20260827 only has 23 days of real history - genuinely untestable
right now, not a modeling gap.

Candidates (all derived from quarterly_income_statement: fiscal_year/fiscal_quarter/net_income/
revenue/eps, reconstructed point-in-time here rather than reusing the live loader's per-symbol
LIMIT-8-quarters logic, which only reflects "as of today," not history):
- consecutive_positive_quarters: trailing streak of quarters (of the most recent 4) with positive
  net_income, counting back from the most recent quarter until the first non-positive one.
- earnings_growth_4q_avg: mean of the 3 QoQ EPS growth rates across the trailing 4 quarters.
- quarterly_growth_momentum: same but for revenue QoQ growth.
- eps_growth_stability: stddev of the 3 QoQ EPS growth rates (needs >=2 valid comparisons).

Reporting lag: quarterly_income_statement has no filing_date column (fiscal_year/fiscal_quarter
only) - approximates each quarter's calendar end (Q1->3/31, Q2->6/30, Q3->9/30, Q4->12/31) plus a
45-day 10-Q filing lag (SEC deadline: 40 days for large accelerated filers, 45 for others -
choosing the more conservative 45 to avoid look-ahead bias), same simplification convention as
every other script in this directory using fiscal_year-12-31 + REPORTING_LAG_DAYS for annual data.

Usage:
    python -m algo.research.growth_quarterly_earnings_quality_candidates
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

CANDIDATES = [
    "consecutive_positive_quarters",
    "earnings_growth_4q_avg",
    "quarterly_growth_momentum",
    "eps_growth_stability",
]

QUARTER_END_MONTH_DAY = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
QUARTERLY_REPORTING_LAG_DAYS = 45


def fetch_quarterly_panel() -> pd.DataFrame:
    sql = """
        SELECT symbol, fiscal_year, fiscal_quarter, net_income, revenue, COALESCE(eps, earnings_per_share) AS eps
        FROM quarterly_income_statement
        WHERE fiscal_year BETWEEN 2000 AND 2026 AND fiscal_quarter BETWEEN 1 AND 4
          AND COALESCE(data_unavailable, false) = false
        ORDER BY symbol, fiscal_year, fiscal_quarter
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "fiscal_year", "fiscal_quarter", "net_income", "revenue", "eps"])
    for c in ["net_income", "revenue", "eps"]:
        df[c] = df[c].astype(float)
    return df


def _quarter_end_date(row: pd.Series) -> pd.Timestamp:
    month, day = QUARTER_END_MONTH_DAY[int(row["fiscal_quarter"])]
    return pd.Timestamp(year=int(row["fiscal_year"]), month=month, day=day)


def build_panel(fund: pd.DataFrame) -> pd.DataFrame:
    fund = fund.sort_values(["symbol", "fiscal_year", "fiscal_quarter"]).reset_index(drop=True)
    fund["quarter_end"] = fund.apply(_quarter_end_date, axis=1)
    fund["known_date"] = fund["quarter_end"] + pd.Timedelta(days=QUARTERLY_REPORTING_LAG_DAYS)

    g = fund.groupby("symbol", group_keys=False)
    ni_pos = (fund["net_income"] > 0).astype(float)
    ni_pos = ni_pos.where(fund["net_income"].notna())

    # Trailing streak of positive-net-income quarters, counting back from THIS quarter, capped
    # at 4 (matches the live loader's own trailing-4-quarter window). Vectorized equivalent of
    # "walk backward from the current row within this symbol until a non-positive quarter."
    def _trailing_streak(s: pd.Series) -> pd.Series:
        out = np.zeros(len(s), dtype=float)
        streak = 0
        vals = s.to_numpy()
        for i, v in enumerate(vals):
            if np.isnan(v):
                streak = 0
                out[i] = np.nan
                continue
            streak = streak + 1 if v > 0 else 0
            out[i] = min(streak, 4)
        return pd.Series(out, index=s.index)

    fund["consecutive_positive_quarters"] = g["net_income"].transform(
        lambda s: _trailing_streak((s > 0).astype(float).where(s.notna()))
    )

    eps_qoq = g["eps"].transform(lambda s: (s - s.shift(1)) / s.shift(1).abs() * 100.0)
    eps_qoq = eps_qoq.where(fund["eps"].notna() & g["eps"].shift(1).notna() & (g["eps"].shift(1) != 0))
    rev_qoq = g["revenue"].transform(lambda s: (s - s.shift(1)) / s.shift(1).abs() * 100.0)
    rev_qoq = rev_qoq.where(fund["revenue"].notna() & g["revenue"].shift(1).notna() & (g["revenue"].shift(1) != 0))

    fund["_eps_qoq"] = eps_qoq
    fund["_rev_qoq"] = rev_qoq
    eps_roll = g["_eps_qoq"].rolling(4, min_periods=1)
    fund["earnings_growth_4q_avg"] = eps_roll.mean().reset_index(level=0, drop=True)
    fund["eps_growth_stability"] = eps_roll.std().reset_index(level=0, drop=True)
    fund["eps_growth_stability"] = fund["eps_growth_stability"].where(
        g["_eps_qoq"].rolling(4, min_periods=1).count().reset_index(level=0, drop=True) >= 2
    )
    fund["quarterly_growth_momentum"] = g["_rev_qoq"].rolling(4, min_periods=1).mean().reset_index(level=0, drop=True)

    # Same overflow/garbage-value guard the live loader applies (near-zero prior-quarter
    # denominator makes a QoQ rate mathematically enormous, not a real signal).
    for c in ["earnings_growth_4q_avg", "quarterly_growth_momentum", "eps_growth_stability"]:
        fund[c] = fund[c].where(fund[c].abs() < 100000)

    out = fund[["symbol", "fiscal_year", "fiscal_quarter", "known_date", *CANDIDATES]].copy()
    return out.dropna(subset=["known_date"])


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def build_records(start_date: str, end_date: str, min_cross_section: int) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    fund = fetch_quarterly_panel()
    panel = build_panel(fund)

    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly = merge_asof_monthly(months, panel, cols=CANDIDATES)

    records = []
    for i in range(len(months) - 1):
        month = months[i]
        qframe = monthly.get(month)
        if qframe is None or qframe.empty:
            continue
        fwd_ret = px.iloc[i + 1] / px.iloc[i] - 1.0
        frame = qframe.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        for c in CANDIDATES:
            frame[c] = _zwinsor(frame[c])
        records.append((month, frame))
    return records


def run(start_date: str, end_date: str, min_cross_section: int, split_date: str) -> None:
    records = build_records(start_date, end_date, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    split_ts = pd.Timestamp(split_date)
    first_half = [r for r in records if pd.Timestamp(r[0]) < split_ts]
    second_half = [r for r in records if pd.Timestamp(r[0]) >= split_ts]

    for label, recs in (
        ("FULL SAMPLE", records),
        (f"FIRST HALF (< {split_date})", first_half),
        (f"SECOND HALF (>= {split_date})", second_half),
    ):
        print(f"--- {label} ({len(recs)} months) ---")
        for c in CANDIDATES:
            usable = [(m, f.dropna(subset=[c])) for m, f in recs]
            usable = [(m, f) for m, f in usable if len(f) >= min_cross_section]
            if not usable:
                print(f"  {c:30s} (no usable months)")
                continue
            avg_n = int(np.mean([len(f) for _, f in usable]))
            result = _fama_macbeth(usable, [c])
            mean, t = result[c]
            print(f"  {c:30s} mean_coef={mean:10.5f}  t_stat={t:7.2f}  n_months={len(usable):4d}  avg_n={avg_n:5d}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--split-date", default="2020-06-01")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.split_date)


if __name__ == "__main__":
    main()
