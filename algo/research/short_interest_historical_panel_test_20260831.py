#!/usr/bin/env python3
"""
Real historical short-interest test, built directly (not via a delegated fork - three
delegation attempts stalled/got mixed up this session; built and run in-session instead).

Corrects a session claim that short interest is "untestable" - that was based on the
PRODUCTION loader (`loaders/load_short_interest_finra.py`) only fetching the last few
settlement cycles for live scoring, NOT on the underlying source's real depth.
`utils.finra_short_interest.FINRAShortInterestFetcher.fetch_date()` takes an arbitrary
historical settlement date. Live-probed this session: real data from 2018-07-31 onward
(15,783-22,341 symbols per date), nothing before 2017-07-31 (0 symbols) - genuine ~8 years
of real depth, not "~2 months".

Panel: for each month-end in the price panel `build_pillar_proxy_records()` already builds
(reused directly, not re-derived - same panel this session's other composite research uses),
attach the most recent FINRA settlement date at least 20 days before that month-end (FINRA
publishes ~2-3 weeks after settlement per this repo's own loader docstring - simple,
disclosed point-in-time discipline, not a precise filing-date lookup). short_pct computed
as short_shares / shares_outstanding, using value_metrics.shares_outstanding_diluted's
CURRENT value as the normalizer (point-in-time historical shares outstanding not available
in the time budget for this pass - a disclosed approximation, same "use what's available,
disclose the gap" convention this project's other research scripts already use elsewhere,
e.g. fama_macbeth_composite_weights.py's own several disclosed simplifications).

Tests short_pct LEVEL and MONTH-OVER-MONTH CHANGE against forward monthly returns, both
univariate and multivariate (controlling for the 5 live pillar proxies from
build_pillar_proxy_records()), Fama-MacBeth (sklearn LinearRegression per month, mean/se
across months - statsmodels isn't installed in this environment, matching every other
script in this project's own convention), first/second-half split, this project's own
|t|>=2-AND-same-sign-both-halves robustness bar.
"""

import logging
import os
import pickle
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from algo.research.fama_macbeth_composite_weights import PILLAR_COLS, build_pillar_proxy_records
from utils.db.context import DatabaseContext
from utils.finra_short_interest import FINRAShortInterestFetcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _candidate_settlement_dates_since(start: date, end: date) -> list[date]:
    """All 15th/end-of-month FINRA settlement dates in [start, end], oldest first."""
    out: list[date] = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        mid = date(y, m, 15)
        if mid >= start:
            out.append(mid)
        nxt_month = date(y, m % 12 + 1, 1) if m < 12 else date(y + 1, 1, 1)
        eom = nxt_month - timedelta(days=1)
        if eom >= start:
            out.append(eom)
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return sorted(d for d in out if start <= d <= end)


def fetch_finra_history(start: date, end: date) -> dict[date, dict[str, float]]:
    """symbol -> short_shares for every real settlement date in range. Skips dates FINRA
    has no data for (pre-~2018) without erroring - real availability, not assumed."""
    fetcher = FINRAShortInterestFetcher()
    out: dict[date, dict[str, float]] = {}
    for d in _candidate_settlement_dates_since(start, end):
        try:
            data = fetcher.fetch_date(d)
        except Exception as exc:
            logger.warning(f"[FINRA] {d}: fetch failed ({exc}), skipping")
            continue
        if not data:
            continue
        out[d] = {sym: float(row.get("short_shares") or 0) for sym, row in data.items()}
        logger.info(f"[FINRA] {d}: {len(data)} symbols")
    return out


def fetch_shares_outstanding() -> pd.Series:
    """company_info_sec.shares_outstanding - the same source/column the PRODUCTION
    load_short_interest_finra.py itself uses to compute short_pct (see that loader's own
    module docstring), not a guessed column name."""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT symbol, shares_outstanding FROM company_info_sec
            WHERE shares_outstanding IS NOT NULL AND shares_outstanding > 0
        """)
        rows = cur.fetchall()
    return pd.Series({r[0]: float(r[1]) for r in rows})


def _load_or_build_pillar_panel(
    cache_path: Path, start_date: str, end_date: str
) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    if cache_path.exists():
        logger.info(f"Loading cached pillar-proxy panel from {cache_path}")
        return cast("list[tuple[pd.Timestamp, pd.DataFrame]]", pickle.loads(cache_path.read_bytes()))
    logger.info("Building pillar-proxy panel (reused from fama_macbeth_composite_weights.py)")
    _partial, _complete, records_raw = build_pillar_proxy_records(start_date, end_date, min_cross_section=300)
    cache_path.write_bytes(pickle.dumps(records_raw))
    return records_raw


def _load_or_fetch_finra_history(cache_path: Path) -> dict[date, dict[str, float]]:
    if cache_path.exists():
        logger.info(f"Loading cached FINRA history from {cache_path}")
        return cast("dict[date, dict[str, float]]", pickle.loads(cache_path.read_bytes()))
    logger.info("Fetching real FINRA short-interest history (2018-01 to 2026-07)")
    finra_hist = fetch_finra_history(date(2018, 1, 1), date(2026, 7, 31))
    cache_path.write_bytes(pickle.dumps(finra_hist))
    return finra_hist


def _merge_short_interest_onto_panel(
    records_raw: list[tuple[pd.Timestamp, pd.DataFrame]],
    finra_hist: dict[date, dict[str, float]],
    settlement_dates: list[date],
    shares_out: pd.Series,
) -> pd.DataFrame:
    rows = []
    for month, frame in records_raw:
        cutoff = pd.Timestamp(month).date() - timedelta(days=20)
        usable = [d for d in settlement_dates if d <= cutoff]
        if len(usable) < 2:
            continue
        d_now, d_prev = usable[-1], usable[-2]
        now_shares = pd.Series(finra_hist[d_now])
        prev_shares = pd.Series(finra_hist[d_prev])
        short_pct = (now_shares / shares_out).clip(0, 2.0) * 100.0  # sanity-bounded 0-200%
        short_pct_prev = (prev_shares / shares_out).clip(0, 2.0) * 100.0
        short_pct_chg = short_pct - short_pct_prev

        sub = frame.copy()
        sub["short_pct"] = short_pct.reindex(sub.index)
        sub["short_pct_chg"] = short_pct_chg.reindex(sub.index)
        sub = sub.dropna(subset=["short_pct", "fwd_ret"])
        if len(sub) < 100:
            continue
        sub["month"] = month
        rows.append(sub)

    if not rows:
        raise RuntimeError("No usable symbol-months after merging FINRA data - aborting")
    return pd.concat(rows)


def run() -> None:
    start_date, end_date = "2018-01-01", "2026-07-01"
    cache_dir = Path(os.environ.get("TEMP", ".")) / "claude" / "short_interest_test_cache_20260831"
    cache_dir.mkdir(parents=True, exist_ok=True)

    records_raw = _load_or_build_pillar_panel(cache_dir / "records_raw.pkl", start_date, end_date)
    logger.info(f"Pillar panel: {len(records_raw)} months")

    finra_hist = _load_or_fetch_finra_history(cache_dir / "finra_hist.pkl")
    settlement_dates = sorted(finra_hist.keys())
    logger.info(f"Got {len(settlement_dates)} real FINRA settlement dates")
    if not settlement_dates:
        raise RuntimeError("No FINRA data fetched at all - aborting rather than faking a result")

    shares_out = fetch_shares_outstanding()
    panel = _merge_short_interest_onto_panel(records_raw, finra_hist, settlement_dates, shares_out)
    logger.info(f"Merged panel: {len(panel)} symbol-months across {panel['month'].nunique()} months")
    print(
        f"\nshort_pct coverage sanity: mean={panel['short_pct'].mean():.2f}%, "
        f"p99={panel['short_pct'].quantile(0.99):.2f}%, max={panel['short_pct'].max():.2f}%"
    )

    def zwinsor(s: pd.Series) -> pd.Series:
        lo, hi = s.quantile([0.01, 0.99])
        s = s.clip(lo, hi)
        std = s.std()
        return (s - s.mean()) / std if std and std > 0 else s * 0.0

    months = sorted(panel["month"].unique())
    half = len(months) // 2
    eras = {"FULL": months, "ERA1": months[:half], "ERA2": months[half:]}

    def fama_macbeth(cols: list[str]) -> dict[str, dict[str, tuple[float, float]]]:
        """Returns {era: {col: (coef_mean, t_stat)}}."""
        out: dict[str, dict[str, tuple[float, float]]] = {}
        for era_name, era_months in eras.items():
            coefs: dict[str, list[float]] = {c: [] for c in cols}
            for m in era_months:
                sub = panel[panel["month"] == m].copy()
                if len(sub) < 100:
                    continue
                x = pd.DataFrame({c: zwinsor(sub[c].astype(float)) for c in cols})
                y = zwinsor(sub["fwd_ret"].astype(float))
                mask = x.notna().all(axis=1) & y.notna()
                if mask.sum() < 100:
                    continue
                reg = LinearRegression().fit(x[mask], y[mask])
                for i, c in enumerate(cols):
                    coefs[c].append(reg.coef_[i])
            era_out = {}
            for c in cols:
                arr = np.array(coefs[c])
                if len(arr) < 5:
                    era_out[c] = (float("nan"), float("nan"))
                    continue
                mean_c = arr.mean()
                se_c = arr.std(ddof=1) / np.sqrt(len(arr))
                era_out[c] = (mean_c, mean_c / se_c if se_c > 0 else float("nan"))
            out[era_name] = era_out
        return out

    print("\n=== UNIVARIATE (short_pct LEVEL only) ===")
    uni_level = fama_macbeth(["short_pct"])
    for era in eras:
        c, t = uni_level[era]["short_pct"]
        print(f"  {era}: coef={c:.5f} t={t:.2f}")

    print("\n=== UNIVARIATE (short_pct CHANGE only) ===")
    uni_chg = fama_macbeth(["short_pct_chg"])
    for era in eras:
        c, t = uni_chg[era]["short_pct_chg"]
        print(f"  {era}: coef={c:.5f} t={t:.2f}")

    print("\n=== MULTIVARIATE (short_pct LEVEL + 5 live pillar proxies) ===")
    multi_level = fama_macbeth(["short_pct", *PILLAR_COLS])
    for era in eras:
        c, t = multi_level[era]["short_pct"]
        print(f"  {era}: coef={c:.5f} t={t:.2f}")

    print("\n=== MULTIVARIATE (short_pct CHANGE + 5 live pillar proxies) ===")
    multi_chg = fama_macbeth(["short_pct_chg", *PILLAR_COLS])
    for era in eras:
        c, t = multi_chg[era]["short_pct_chg"]
        print(f"  {era}: coef={c:.5f} t={t:.2f}")

    def robust(era_dict: dict[str, dict[str, tuple[float, float]]], col: str) -> bool:
        t_full, t_e1, t_e2 = era_dict["FULL"][col][1], era_dict["ERA1"][col][1], era_dict["ERA2"][col][1]
        if any(np.isnan([t_full, t_e1, t_e2])):
            return False
        same_sign = (t_e1 > 0) == (t_e2 > 0)
        return same_sign and abs(t_e1) >= 2.0 and abs(t_e2) >= 2.0

    print("\n=== VERDICT (|t|>=2 AND same sign in BOTH half-splits) ===")
    print(f"  short_pct level, univariate:   robust={robust(uni_level, 'short_pct')}")
    print(f"  short_pct change, univariate:  robust={robust(uni_chg, 'short_pct_chg')}")
    print(f"  short_pct level, multivariate: robust={robust(multi_level, 'short_pct')}")
    print(f"  short_pct change, multivariate: robust={robust(multi_chg, 'short_pct_chg')}")


if __name__ == "__main__":
    run()
