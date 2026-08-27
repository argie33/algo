#!/usr/bin/env python3
"""
First-principles, pillar-agnostic diagnostic: merges every raw input this repo has computed
across Quality/Value/Growth/Momentum/Risk into ONE monthly panel, strips pillar labels, and
asks two questions the pillar-by-pillar Fama-MacBeth work never asked directly:

1. Does the DATA's own correlation structure (hierarchical clustering) group inputs the way the
   existing pillar taxonomy assumes, or differently?
2. In one joint ML model over ALL inputs at once (not pillar-by-pillar), which inputs actually
   carry independent importance - regardless of which pillar they currently live in or whether
   they're currently scored at all?

Built 2026-08-27 (goal: user directly questioned whether this session's factor work has been
anchored on the existing pillar structure rather than asking what the data itself supports).

CAVEAT, not swept under the rug: this system has ~10-12 years of history (~127-151 months
depending on which fundamentals require how many trailing years). A joint model over 50+ raw
features has LESS independent data per feature than any single-pillar test already run this
session. Treat clustering/importance results here as suggestive of where to look closer, not as
a final answer on weights - same discipline this whole project has already applied to every
other finding (half-split before trusting, small-sample caution).

Reuses existing panel-construction helpers from the sibling Fama-MacBeth scripts rather than
re-deriving fetch/ratio logic - see imports below.
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd
import shap
from scipy.cluster.hierarchy import fcluster, linkage
from sklearn.ensemble import HistGradientBoostingRegressor

from algo.research.fama_macbeth_growth_factors import (
    build_growth_panel,
    fetch_annual_fundamentals,
    merge_asof_monthly,
)
from algo.research.fama_macbeth_momentum_factors import compute_daily_indicators, fetch_daily_prices
from algo.research.fama_macbeth_price_factors import build_monthly_cross_sections, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.fama_macbeth_value_factors import build_value_panel, compute_ratios, fetch_annual_value_fundamentals

logger = logging.getLogger(__name__)

QUALITY_COLS = [
    "roe",
    "roa",
    "operating_margin",
    "net_margin",
    "debt_to_assets",
    "interest_coverage",
    "gross_profitability",
    "operating_profitability",
    "accruals_ratio",
    "payout_ratio",
    "roic_pct",
    "altman_z_score",
    "roce",
    "fcf_margin",
    "debt_to_equity",
    "current_ratio",
    "share_issuance_yoy",
    "debt_issuance_yoy",
    "margin_volatility_3y",
    "fcf_to_net_income",
    "net_debt_to_ebitda",
    "net_debt_to_fcf",
]
VALUE_COLS = ["pe", "pb", "ps", "fcf_yield", "dividend_yield", "ev_ebitda", "ev_revenue", "size"]
GROWTH_COLS = [
    "eps_growth_1y",
    "eps_growth_3y",
    "eps_growth_5y",
    "revenue_growth_1y",
    "revenue_growth_3y",
    "revenue_growth_5y",
    "ni_growth_yoy",
    "oi_growth_yoy",
    "fcf_growth_yoy",
    "ocf_growth_yoy",
    "asset_growth_yoy_flipped",
    "sustainable_growth_rate_approx",
]
PRICE_COLS = ["mom_12_1", "mom_6m", "mom_3m", "str_1m", "vol", "downside_vol", "beta", "max_dd"]
TECH_COLS = ["rsi_14", "macd_sign", "price_vs_sma_50", "price_vs_sma_200"]

ALL_COLS = QUALITY_COLS + VALUE_COLS + GROWTH_COLS + PRICE_COLS + TECH_COLS
PILLAR_OF = (
    dict.fromkeys(QUALITY_COLS, "Quality")
    | dict.fromkeys(VALUE_COLS, "Value")
    | dict.fromkeys(GROWTH_COLS, "Growth")
    | dict.fromkeys(PRICE_COLS, "Momentum/Risk (price)")
    | dict.fromkeys(TECH_COLS, "Momentum (technical)")
)


def _zwinsor(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def fetch_tech_month_end(start_date: str, end_date: str) -> pd.DataFrame:
    daily = fetch_daily_prices(start_date, end_date)
    daily = compute_daily_indicators(daily)
    # NOTE: matches fetch_month_end_prices' month-key convention exactly - date_trunc('month',
    # date), i.e. FIRST-of-month timestamp (even though the price itself is the LAST trading
    # day's close that month) - .dt.to_timestamp() defaults to period-start, not period-end.
    daily["month"] = daily["date"].dt.to_period("M").dt.to_timestamp()
    idx = daily.groupby(["symbol", "month"])["date"].idxmax()
    monthly = daily.loc[idx, ["symbol", "month", *TECH_COLS]].reset_index(drop=True)
    return monthly


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Fetching fundamentals panels")
    quality_fund = fetch_annual_quality_fundamentals()
    quality_panel = build_quality_panel(quality_fund)

    growth_fund = fetch_annual_fundamentals()
    growth_panel = build_growth_panel(growth_fund)
    # SGR approximation reusing quality_panel's roe/payout_ratio (retention = 1-payout) rather
    # than building a 4th separate fundamentals fetch - a deliberate simplification for this
    # broad-strokes diagnostic, not the exact production/composite-weights-script formula.
    sgr_src = quality_panel[["symbol", "fiscal_year", "roe", "payout_ratio"]].copy()
    sgr_src["sustainable_growth_rate_approx"] = sgr_src["roe"] * (1.0 - sgr_src["payout_ratio"].fillna(0).clip(0, 1))
    growth_panel = growth_panel.merge(
        sgr_src[["symbol", "fiscal_year", "sustainable_growth_rate_approx"]], on=["symbol", "fiscal_year"], how="left"
    )

    value_fund = fetch_annual_value_fundamentals()
    value_panel_raw = build_value_panel(value_fund)

    logger.info(f"Pulling month-end prices {start_date}..{end_date}")
    px_df = fetch_month_end_prices(start_date, end_date)
    px = px_df.pivot(index="month", columns="symbol", values="px").sort_index()
    ret = px.pct_change(fill_method=None)

    logger.info("Building price-factor monthly cross-sections (mom/vol/beta/drawdown)")
    price_records = build_monthly_cross_sections(
        px, ret, beta_window=24, vol_window=12, min_cross_section=min_cross_section
    )
    if not price_records:
        raise RuntimeError("No usable price cross-sections")
    months = pd.DatetimeIndex([m for m, _ in price_records])

    logger.info("Fetching daily prices for RSI/MACD/SMA technical indicators")
    tech_monthly = fetch_tech_month_end(start_date, end_date)

    logger.info("As-of merging fundamentals onto the price panel's months")
    quality_monthly = merge_asof_monthly(months, quality_panel, cols=QUALITY_COLS)
    growth_monthly = merge_asof_monthly(months, growth_panel, cols=GROWTH_COLS)
    value_monthly = merge_asof_monthly(
        months,
        value_panel_raw,
        cols=[c for c in value_panel_raw.columns if c not in ("symbol", "fiscal_year", "known_date")],
    )

    pooled_frames: list[pd.DataFrame] = []
    for month_raw, price_frame in price_records:
        # price_records' month keys come from px.index, which is built from a raw SQL DATE
        # column - psycopg2 returns those as datetime.date, not pd.Timestamp. months/
        # *_monthly dicts above were built via pd.DatetimeIndex(...), which normalizes to
        # Timestamp - datetime.date and Timestamp compare equal but do NOT reliably hash equal,
        # so a dict .get(month_raw) silently misses every single month. Normalize here.
        month = pd.Timestamp(month_raw)
        q = quality_monthly.get(month)
        g = growth_monthly.get(month)
        v_raw = value_monthly.get(month)
        if q is None or g is None or v_raw is None or q.empty or g.empty or v_raw.empty:
            logger.info(
                f"{month}: SKIP early - q_none={q is None} g_none={g is None} v_none={v_raw is None} "
                f"q_len={len(q) if q is not None else -1} g_len={len(g) if g is not None else -1} "
                f"v_len={len(v_raw) if v_raw is not None else -1}"
            )
            continue
        price_at_month = px.loc[month_raw] if month_raw in px.index else None
        if price_at_month is None:
            logger.info(f"{month}: SKIP - not in px.index")
            continue
        v = compute_ratios(v_raw, price_at_month)
        v = v[VALUE_COLS]

        tech = tech_monthly[tech_monthly["month"] == month].set_index("symbol")[TECH_COLS]

        frame = price_frame.join(q, how="inner").join(g, how="inner").join(v, how="inner").join(tech, how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        if len(frame) < min_cross_section:
            logger.info(
                f"{month}: price={len(price_frame)} q={len(q)} g={len(g)} v={len(v)} tech={len(tech)} "
                f"joined={len(frame)} < min={min_cross_section}, skipping"
            )
            continue

        for col in QUALITY_COLS + GROWTH_COLS + VALUE_COLS + TECH_COLS:
            frame[col] = _zwinsor(frame[col].astype(float))
        # PRICE_COLS already z-scored by build_monthly_cross_sections; fwd_ret left as-is.

        frame["month"] = month
        pooled_frames.append(frame)

    if not pooled_frames:
        raise RuntimeError("No usable joint-panel months after merging all pillars")

    panel = pd.concat(pooled_frames, ignore_index=True)
    print(f"\nJoint panel: {len(panel)} symbol-months across {panel['month'].nunique()} months, {len(ALL_COLS)} inputs")
    print(f"Months: {panel['month'].min()} to {panel['month'].max()}\n")

    # --- Analysis 1: correlation-based hierarchical clustering, pillar-agnostic ---
    corr = panel[ALL_COLS].corr()
    dist = 1.0 - corr.abs()
    np.fill_diagonal(dist.values, 0.0)
    condensed = dist.values[np.triu_indices(len(ALL_COLS), k=1)]
    linkage_matrix = linkage(condensed, method="average")
    for n_clusters in (8, 12):
        cluster_ids = fcluster(linkage_matrix, t=n_clusters, criterion="maxclust")
        print(f"=== Hierarchical clustering, {n_clusters} clusters (pillar-agnostic) ===")
        clusters: dict[int, list[str]] = {}
        for col, cid in zip(ALL_COLS, cluster_ids, strict=True):
            clusters.setdefault(cid, []).append(col)
        for cid, cols in sorted(clusters.items()):
            pillars_in_cluster = sorted({PILLAR_OF[c] for c in cols})
            mixed = "MIXED-PILLAR" if len(pillars_in_cluster) > 1 else "single-pillar"
            print(f"  cluster {cid} [{mixed}, pillars={pillars_in_cluster}]: {cols}")
        print()

    # --- Analysis 2: one joint walk-forward ML importance ranking over ALL inputs ---
    panel["year"] = panel["month"].dt.year
    years = sorted(panel["year"].unique())
    test_years = years[max(1, int(len(years) * 0.6)) :]
    print(f"=== Joint ML importance (walk-forward, test years {test_years}) ===")
    all_shap = []
    for test_year in test_years:
        train = panel[panel["year"] < test_year]
        test = panel[panel["year"] == test_year]
        if train.empty or len(test) < min_cross_section:
            continue
        model = HistGradientBoostingRegressor(
            max_iter=200, max_depth=4, learning_rate=0.05, l2_regularization=1.0, random_state=0
        )
        model.fit(train[ALL_COLS], train["fwd_ret"])
        sample = test.sample(n=min(800, len(test)), random_state=0)
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(sample[ALL_COLS])
        all_shap.append(np.abs(shap_values))
        logger.info(f"{test_year}: train={len(train)} test={len(test)} sampled={len(sample)}")

    if all_shap:
        importance = np.concatenate(all_shap, axis=0).mean(axis=0)
        order = np.argsort(-importance)
        print(f"{'rank':4s} {'input':28s} {'pillar':24s} {'mean|SHAP|':>10s}")
        for rank, idx in enumerate(order[:25], 1):
            col = ALL_COLS[idx]
            print(f"{rank:4d} {col:28s} {PILLAR_OF[col]:24s} {importance[idx]:10.5f}")
    else:
        print("No usable OOS years for joint ML importance.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=300)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
