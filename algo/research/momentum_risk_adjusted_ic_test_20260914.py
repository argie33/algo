#!/usr/bin/env python3
"""
Does risk-adjusting Momentum (the real MSCI Momentum Index construction - divide each
price-return window by realized volatility before combining, instead of scoring raw returns)
actually move the composite's forward-return IC/t-stat? Built 2026-09-14, direct next step in
the goal-session sequence recorded in MEMORY.md's 20260914 backtest finding: the disciplined
fit(2017-2021)/holdout(2022-2026) test found the CURRENT composite's real predictive power is
not distinguishable from zero (full-sample IC=0.0158, t=1.08), and naive sector/size
neutralization made it WORSE, not better (composite_neutral). Per that finding's own stated
sequence, no more formula changes should ship on faith before checking whether they actually
move this number - this script is that check, isolated to the single change (risk-adjusting
Momentum's two return-window inputs), nothing else touched.

MSCI's real Risk-Adjusted Momentum construction (MSCI Momentum Index Methodology, live-verified
against the same academic/institutional-convergent evidence class already used for this pillar's
2026-09-14 mom_12_1 reweight - see loaders/stock_scores/momentum_scoring.py's docstring):
compute each price-return window (MSCI uses 6m and 12m local price return, this repo's momentum
pillar uses mom_3m and mom_12_1), then divide each by the annualized standard deviation of daily
(MSCI: weekly) local price returns over a trailing realized-vol window, BEFORE z-scoring and
combining - a Sharpe-ratio-style risk adjustment, not a raw-return score. This isolates that one
change: mom_3m and mom_12_1 both risk-adjusted by the same trailing-252-trading-day annualized
daily-return vol (reusing the identical vol_252d construction fama_macbeth_composite_weights.py's
stability_proxy already computes, so the risk adjustment is CONSISTENT with the Risk pillar's own
data, not a separately-invented vol convention) - tech_trend/sma_avg (not price-return momentum,
no MSCI risk-adjustment concept applies to them) are left untouched, exactly as they are in the
live/current momentum_proxy construction, for a clean single-variable comparison.

DELIBERATELY NOT touching fama_macbeth_composite_weights.py's shared build_pillar_proxy_records()
or loaders/stock_scores/momentum_scoring.py (live scoring) in this pass - this script recomputes
its own momentum-only panel (same duplication convention every other per-pillar FM script in this
directory already uses, e.g. fama_macbeth_momentum_factors.py's own independent
compute_daily_indicators/build_month_end_panel calls) so the shared builder other scripts depend
on isn't touched by an unvalidated experiment. If this shows a real IC/t-stat improvement, the
next step is porting it into both the shared proxy builder and live scoring - not before.

Usage:
    python -m algo.research.momentum_risk_adjusted_ic_test_20260914 [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import (
    PILLAR_COLS,
    PILLAR_TO_LIVE_KEY,
    _zwinsor,
    build_pillar_proxy_records,
)
from algo.research.fama_macbeth_momentum_factors import (
    build_month_end_panel,
    compute_daily_indicators,
)
from algo.research.fama_macbeth_momentum_factors import (
    fetch_daily_prices as fetch_daily_close,
)
from algo.research.fama_macbeth_price_factors import (
    _trailing_cumret,
    fetch_month_end_prices,
    print_survivorship_bias_caveat,
)
from loaders.stock_scores.pillar_weights import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)


def build_momentum_variants(start_date: str, end_date: str) -> dict[pd.Timestamp, pd.DataFrame]:
    """Independently recomputes month x symbol frames of {momentum_proxy_current,
    momentum_proxy_riskadj} - the ONLY two things this script needs beyond what
    build_pillar_proxy_records() already returns for the other 4 pillars. Mirrors that
    function's own momentum/vol construction verbatim (same _trailing_cumret/vol_252d shapes)
    so the comparison isolates the risk-adjustment step alone, not an incidental construction
    difference.
    """
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index
    months_period = pd.PeriodIndex(months, freq="M")

    daily_close = fetch_daily_close(start_date, end_date)
    daily_wide = daily_close.pivot(index="date", columns="symbol", values="px").sort_index()
    daily_ret = daily_wide.pct_change(fill_method=None)
    daily_dates = daily_wide.index

    daily_close = compute_daily_indicators(daily_close)
    _px_daily, indicators = build_month_end_panel(daily_close)
    for key in indicators:
        indicators[key] = (
            indicators[key].set_axis(pd.PeriodIndex(indicators[key].index, freq="M")).reindex(months_period)
        )

    month_to_daily_idx: dict[pd.Timestamp, int | None] = {}
    for month in months:
        cutoff = pd.Timestamp(month) + pd.offsets.MonthEnd(0)
        pos = int(daily_dates.searchsorted(cutoff, side="right")) - 1
        month_to_daily_idx[month] = pos if pos >= 0 else None

    out: dict[pd.Timestamp, pd.DataFrame] = {}
    for i, month in enumerate(months):
        daily_idx = month_to_daily_idx.get(month)
        if daily_idx is None or daily_idx < 251 or i < 12:
            continue

        mom_3m = _trailing_cumret(px, i, 3)
        mom_12_1 = _trailing_cumret(px, i - 1, 11)
        rsi = indicators["rsi_14"].iloc[i]
        macd_sign = indicators["macd_sign"].iloc[i]
        tech_trend = (_zwinsor(rsi) + _zwinsor(macd_sign)) / 2.0
        sma_avg = (
            _zwinsor(indicators["price_vs_sma_50"].iloc[i]) + _zwinsor(indicators["price_vs_sma_200"].iloc[i])
        ) / 2.0

        # Same trailing-252-trading-day annualized daily-return vol as
        # fama_macbeth_composite_weights.py's stability_proxy (vol_252d) - reusing that exact
        # construction rather than inventing a separate one, so the risk adjustment sits on the
        # same footing as the Risk pillar's own already-validated volatility measure.
        win252 = daily_ret.iloc[daily_idx - 251 : daily_idx + 1]
        vol_252d = win252.std() * np.sqrt(252)
        vol_252d = vol_252d.reindex(mom_3m.index)

        # MSCI Risk-Adjusted Momentum: each return window / realized vol, BEFORE z-scoring.
        # Guarded against near-zero/negative vol (illiquid or barely-traded symbols) - those
        # become NaN rather than an exploding ratio.
        safe_vol = vol_252d.where(vol_252d > 1e-4)
        mom_3m_riskadj = mom_3m / safe_vol
        mom_12_1_riskadj = mom_12_1 / safe_vol

        momentum_proxy_current = 0.25 * (_zwinsor(mom_3m) + _zwinsor(mom_12_1) + tech_trend + sma_avg)
        momentum_proxy_riskadj = 0.25 * (_zwinsor(mom_3m_riskadj) + _zwinsor(mom_12_1_riskadj) + tech_trend + sma_avg)

        # NORMALIZED to pd.Timestamp (matching run()'s `pd.Timestamp(month_raw)` lookup key) -
        # fetch_month_end_prices' "month" column comes back as plain datetime.date (same gotcha
        # barra_style_neutralized_composite_20260907.py's own module docstring already documents
        # and guards against), so leaving this dict keyed by the raw px.index type made every
        # run() lookup below silently miss - the exact failure that produced "No usable months
        # after merge" on first run.
        out[pd.Timestamp(month)] = pd.DataFrame(
            {
                "momentum_proxy_current": momentum_proxy_current,
                "momentum_proxy_riskadj": momentum_proxy_riskadj,
            }
        )

    return out


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    print_survivorship_bias_caveat()
    logger.info("Building base pillar-proxy panel (growth/value/quality/risk/momentum_current)")
    _rp, _rc, records_raw = build_pillar_proxy_records(start_date, end_date, min_cross_section)

    logger.info("Recomputing momentum variants (current vs risk-adjusted)")
    mom_variants = build_momentum_variants(start_date, end_date)

    other_pillars = [c for c in PILLAR_COLS if c != "momentum_proxy"]
    live_weight_map = {c: BASE_PILLAR_WEIGHTS[k] for c, k in PILLAR_TO_LIVE_KEY.items()}

    merged: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for month_raw, raw in records_raw:
        month = pd.Timestamp(month_raw)
        mv = mom_variants.get(month)
        if mv is None or mv.empty:
            continue

        df = raw.copy()
        df["momentum_proxy_riskadj"] = mv["momentum_proxy_riskadj"].reindex(df.index)
        # Recomputed independently rather than reused verbatim from records_raw - overwrite so
        # both momentum columns come from the exact same recomputation pass (same universe/vol
        # inputs), keeping the A/B comparison apples-to-apples.
        df["momentum_proxy_current"] = mv["momentum_proxy_current"].reindex(df.index)

        df = df.dropna(subset=["fwd_ret", "momentum_proxy_current", "momentum_proxy_riskadj", *other_pillars])
        if len(df) < min_cross_section:
            continue

        for col in [*other_pillars, "momentum_proxy_current", "momentum_proxy_riskadj"]:
            df[col] = _zwinsor(df[col])

        df["composite_current"] = sum(df[c] * live_weight_map[c] for c in other_pillars) + (
            df["momentum_proxy_current"] * live_weight_map["momentum_proxy"]
        )
        df["composite_riskadj_momentum"] = sum(df[c] * live_weight_map[c] for c in other_pillars) + (
            df["momentum_proxy_riskadj"] * live_weight_map["momentum_proxy"]
        )

        merged.append((month, df))

    if not merged:
        raise RuntimeError("No usable months after merge - check date range / min_cross_section")

    logger.info(f"{len(merged)} usable months: {merged[0][0]} to {merged[-1][0]}")

    def _ic_series(records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> list[float]:
        out = []
        for _m, f in records:
            g = f.dropna(subset=[col, "fwd_ret"])
            if len(g) < 20:
                continue
            out.append(g[col].corr(g["fwd_ret"], method="spearman"))
        return [c for c in out if not np.isnan(c)]

    def _report(label: str, corrs: list[float]) -> None:
        arr = np.array(corrs)
        if len(arr) == 0:
            print(f"  {label:32s}  no usable months")
            return
        mean = arr.mean()
        se = arr.std(ddof=1) / np.sqrt(len(arr)) if len(arr) > 1 else float("nan")
        t = mean / se if se and se > 0 else float("nan")
        print(f"  {label:32s}  mean_IC={mean:8.4f}  t={t:7.2f}  n_months={len(arr):4d}")

    cols = [
        "momentum_proxy_current",
        "momentum_proxy_riskadj",
        "composite_current",
        "composite_riskadj_momentum",
    ]

    fit_period = [(m, f) for m, f in merged if m.year <= 2021]
    holdout_period = [(m, f) for m, f in merged if m.year >= 2022]

    print(f"\n########## FULL SAMPLE ({merged[0][0]} to {merged[-1][0]}, {len(merged)} months) ##########")
    for c in cols:
        _report(c, _ic_series(merged, c))

    print(f"\n########## FIT PERIOD 2017-2021 ({len(fit_period)} months) ##########")
    for c in cols:
        _report(c, _ic_series(fit_period, c))

    print(f"\n########## TRUE HOLDOUT 2022-2026 ({len(holdout_period)} months) - NEVER touched above ##########")
    for c in cols:
        _report(c, _ic_series(holdout_period, c))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2015-06-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
