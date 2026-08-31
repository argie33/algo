#!/usr/bin/env python3
"""
Follow-up to goal2_joint_raw_input_vs_pillar_composite.py (rebuilt/committed 1c97c2c9e this
session): that script's joint HistGradientBoostingRegressor over 69 raw inputs LOST to the
linear pillar-then-combine composite overall (Spearman 0.0455 vs 0.0709) - real evidence that
flat data-driven combination isn't leaving much on the table in aggregate. But trees capture
interactions automatically, and "loses overall" doesn't rule out ONE OR TWO specific raw-metric
interactions the tree relies on that a linear pillar composite structurally can't use even if
its other components are individually weaker/noisier (overfitting elsewhere). This script:

1. Rebuilds the identical panel + final_tree fit goal2's own script does (same functions,
   same year-cutoff, same hyperparameters - no drift from what's already been verified).
2. Extracts pairwise interaction strength among the top-20-importance features via a 2D partial
   dependence surface vs. the additive sum of each feature's own 1D partial dependence - the
   deviation IS the interaction effect (a discrete approximation of Friedman's H-statistic).
3. For the top candidate pairs, runs a PROPER Fama-MacBeth test (per-month cross-sectional
   z-score + OLS of fwd_ret on main effects + interaction term, first/second half split) against
   this project's own |t|>=2-both-halves-same-sign robustness bar - the tree's internal reliance
   on a pair is a LEAD, not evidence on its own (see this project's own history of SHAP/tree
   findings that didn't survive proper multivariate+half-split testing, e.g. the sparse-lasso
   pillar-preference artifact in composite_ml_vs_linear_stress_tested_via_user_pushback_20260827).
4. Cross-references: does the already-live, already-robust Value x Risk interaction
   (VALUE_RISK_INTERACTION_MAX_SHIFT in loaders/load_stock_scores.py) show up near the top of the
   tree's own interaction ranking, as a sanity check that this method finds real things?

Uncommitted by design - a diagnostic follow-up, not a production or even a standing research
artifact goal2's own script is.
"""

import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import partial_dependence, permutation_importance

from algo.research.fama_macbeth_growth_factors import build_growth_panel, fetch_annual_fundamentals, merge_asof_monthly
from algo.research.fama_macbeth_price_factors import build_monthly_cross_sections, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.fama_macbeth_value_factors import build_value_panel, compute_ratios, fetch_annual_value_fundamentals
from algo.research.goal2_joint_raw_input_vs_pillar_composite import (
    ALL_COLS,
    GROWTH_COLS,
    NEW_ANNUAL_COLS,
    NEW_MONTHLY_COLS,
    PILLAR_OF,
    QUALITY_COLS,
    TECH_COLS,
    VALUE_COLS,
    _compute_daily_risk_windows,
    _zwinsor,
    build_extended_annual_panel,
    compute_price_dependent_new_cols,
    fetch_extended_annual,
    fetch_tech_and_daily_returns,
    live_linear_score,
)

logger = logging.getLogger(__name__)


def build_panel(start_date: str, end_date: str, min_cross_section: int) -> pd.DataFrame:
    """Verbatim re-derivation of goal2's own run() panel-build loop (same functions, same
    order) - goal2's run() doesn't expose the intermediate panel, so this reconstructs it by
    calling the exact same already-verified building blocks rather than re-deriving formulas."""
    quality_fund = fetch_annual_quality_fundamentals()
    quality_panel = build_quality_panel(quality_fund)
    quality_panel = quality_panel.merge(
        quality_fund[["symbol", "fiscal_year", "revenue", "total_assets"]], on=["symbol", "fiscal_year"], how="left"
    )
    quality_panel["asset_turnover"] = np.where(
        quality_panel["total_assets"] > 0, quality_panel["revenue"] / quality_panel["total_assets"], np.nan
    )

    growth_fund = fetch_annual_fundamentals()
    growth_panel = build_growth_panel(growth_fund)
    sgr_src = quality_panel[["symbol", "fiscal_year", "roe", "payout_ratio"]].copy()
    sgr_src["sustainable_growth_rate_approx"] = sgr_src["roe"] * (1.0 - sgr_src["payout_ratio"].fillna(0).clip(0, 1))
    growth_panel = growth_panel.merge(
        sgr_src[["symbol", "fiscal_year", "sustainable_growth_rate_approx"]], on=["symbol", "fiscal_year"], how="left"
    )

    value_fund = fetch_annual_value_fundamentals()
    value_panel_raw = build_value_panel(value_fund)

    ext_fund = fetch_extended_annual()
    ext_panel = build_extended_annual_panel(ext_fund)

    px_df = fetch_month_end_prices(start_date, end_date)
    px = px_df.pivot(index="month", columns="symbol", values="px").sort_index()
    ret = px.pct_change(fill_method=None)
    mkt = ret["SPY"] if "SPY" in ret.columns else None

    price_records = build_monthly_cross_sections(
        px, ret, beta_window=24, vol_window=12, min_cross_section=min_cross_section
    )
    if not price_records:
        raise RuntimeError("No usable price cross-sections")
    months = pd.DatetimeIndex([m for m, _ in price_records])

    tech_monthly, daily_wide, daily_ret = fetch_tech_and_daily_returns(start_date, end_date)
    daily_dates = daily_wide.index
    month_to_daily_idx: dict[pd.Timestamp, int | None] = {}
    for month_raw, _ in price_records:
        cutoff = pd.Timestamp(month_raw) + pd.offsets.MonthEnd(0)
        pos = int(daily_dates.searchsorted(cutoff, side="right")) - 1
        month_to_daily_idx[month_raw] = pos if pos >= 0 else None

    quality_monthly = merge_asof_monthly(months, quality_panel, cols=QUALITY_COLS)
    growth_monthly = merge_asof_monthly(months, growth_panel, cols=GROWTH_COLS)
    value_monthly = merge_asof_monthly(
        months,
        value_panel_raw,
        cols=[c for c in value_panel_raw.columns if c not in ("symbol", "fiscal_year", "known_date")],
    )
    ext_cols = [
        "ebit_per_share",
        "owner_earnings_per_share",
        "net_debt_per_share",
        "shares_diluted",
        "reinvestment_rate",
        "book_value_growth",
        "rd_intensity",
        "net_debt_issuance_yoy",
        "total_assets_for_log",
        "revenue_for_log",
        "net_debt_for_ev",
    ]
    ext_monthly = merge_asof_monthly(months, ext_panel, cols=ext_cols)

    pooled_frames = []
    for i, (month_raw, price_frame) in enumerate(price_records):
        month = pd.Timestamp(month_raw)
        q = quality_monthly.get(month)
        gm = growth_monthly.get(month)
        v_raw = value_monthly.get(month)
        e_raw = ext_monthly.get(month)
        if any(x is None or x.empty for x in (q, gm, v_raw, e_raw)):
            continue
        if month_raw not in px.index:
            continue
        price_at_month = px.loc[month_raw]
        v = compute_ratios(v_raw, price_at_month)[VALUE_COLS]
        e_new = compute_price_dependent_new_cols(e_raw, price_at_month)
        tech = tech_monthly[tech_monthly["month"] == month].set_index("symbol")[TECH_COLS]

        frame = (
            price_frame.join(q, how="inner")
            .join(gm, how="inner")
            .join(v, how="inner")
            .join(tech, how="inner")
            .join(e_new, how="left")
        )

        if mkt is not None and i >= 12:
            win = ret.iloc[i - 11 : i + 1]
            mkt_win = mkt.iloc[i - 11 : i + 1]
            mkt_var = mkt_win.var()
            local_beta = (
                win.apply(lambda col, m=mkt_win: col.cov(m)) / mkt_var
                if mkt_var and mkt_var > 0
                else pd.Series(np.nan, index=win.columns)
            )
            resid = win - pd.DataFrame(
                np.outer(mkt_win.values, local_beta.values), index=win.index, columns=win.columns
            )
            idio_vol = (resid.std() * np.sqrt(12)).reindex(frame.index)
        else:
            idio_vol = pd.Series(np.nan, index=frame.index)
        frame["idio_vol"] = idio_vol

        if mkt is not None and i >= 36:
            win_db = ret.iloc[i - 35 : i + 1]
            mkt_db = mkt.iloc[i - 35 : i + 1]
            down_mask = mkt_db < 0
            if down_mask.sum() >= 8:
                mkt_down = mkt_db[down_mask]
                win_down = win_db[down_mask]
                mkt_down_var = mkt_down.var()
                downside_beta = (
                    (win_down.apply(lambda col, m=mkt_down: col.cov(m)) / mkt_down_var).reindex(frame.index)
                    if mkt_down_var and mkt_down_var > 0
                    else pd.Series(np.nan, index=frame.index)
                )
            else:
                downside_beta = pd.Series(np.nan, index=frame.index)
        else:
            downside_beta = pd.Series(np.nan, index=frame.index)
        frame["downside_beta"] = downside_beta

        daily_idx = month_to_daily_idx.get(month_raw)
        vol_60d, vol_252d, max_dd_1y = _compute_daily_risk_windows(daily_idx, daily_ret, daily_wide, frame.index)
        frame["vol_60d"] = vol_60d
        frame["vol_252d"] = vol_252d
        frame["max_dd_1y"] = max_dd_1y

        frame = frame.replace([np.inf, -np.inf], np.nan)
        if len(frame) < min_cross_section:
            continue

        # Keep an UN-imputed, per-panel-z-scored copy for the tree (matches goal2 exactly) AND
        # keep the raw (pre-fillna) values around for the later per-month Fama-MacBeth pass,
        # which needs its own per-MONTH z-scoring, not goal2's global one.
        frame_raw = frame.copy()
        for col in (
            QUALITY_COLS
            + GROWTH_COLS
            + VALUE_COLS
            + TECH_COLS
            + NEW_ANNUAL_COLS
            + NEW_MONTHLY_COLS
            + ["vol_60d", "vol_252d", "max_dd_1y"]
        ):
            frame[col] = _zwinsor(frame[col].astype(float))

        frame["live_linear"] = live_linear_score(frame)
        frame["month"] = month
        frame["year"] = month.year
        frame_raw["month"] = month
        frame_raw["fwd_ret"] = frame["fwd_ret"]
        pooled_frames.append((frame, frame_raw))

    if not pooled_frames:
        raise RuntimeError("No usable joint-panel months")

    panel = pd.concat([f for f, _ in pooled_frames], ignore_index=True)
    panel_raw = pd.concat([r for _, r in pooled_frames], ignore_index=True)
    return panel, panel_raw


def fama_macbeth_interaction(panel_raw: pd.DataFrame, col_a: str, col_b: str) -> dict[str, dict[str, Any] | None]:
    """Per-month cross-sectional z-score + OLS of fwd_ret on [zA, zB, zA*zB], Fama-MacBeth
    averaging across months (mean coef / (std(coef)/sqrt(n_months)) = t-stat), full sample +
    first-half/second-half split - same discipline as composite_percentile_and_interaction_test_20260831.py."""
    months = sorted(panel_raw["month"].unique())

    def _run(month_list: list[Any]) -> dict[str, Any] | None:
        coefs = []
        for m in month_list:
            sub = panel_raw[panel_raw["month"] == m][[col_a, col_b, "fwd_ret"]].dropna()
            if len(sub) < 30:
                continue
            za = (sub[col_a] - sub[col_a].mean()) / sub[col_a].std() if sub[col_a].std() > 0 else None
            zb = (sub[col_b] - sub[col_b].mean()) / sub[col_b].std() if sub[col_b].std() > 0 else None
            if za is None or zb is None:
                continue
            zab = za * zb
            x = np.column_stack([np.ones(len(sub)), za.to_numpy(), zb.to_numpy(), zab.to_numpy()])
            y = sub["fwd_ret"].to_numpy()
            try:
                beta, *_ = np.linalg.lstsq(x, y, rcond=None)
            except Exception:
                continue
            coefs.append(beta)  # [const, a, b, ab]
        if len(coefs) < 6:
            return None
        arr = np.array(coefs)
        mean = arr.mean(axis=0)
        se = arr.std(axis=0, ddof=1) / np.sqrt(len(arr))
        t = mean / np.where(se == 0, np.nan, se)
        return {"n_months": len(arr), "coef": mean, "t": t}

    full = _run(months)
    half = len(months) // 2
    era1 = _run(months[:half])
    era2 = _run(months[half:])
    return {"full": full, "era1": era1, "era2": era2}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Building panel (same construction as goal2_joint_raw_input_vs_pillar_composite.run())")
    panel, panel_raw = build_panel("2014-01-01", "2026-08-31", 300)
    panel[ALL_COLS] = panel[ALL_COLS].fillna(0.0)
    logger.info(f"Panel built: {len(panel)} symbol-months, {panel['month'].nunique()} months")

    years = sorted(panel["year"].unique())
    test_years = years[max(1, int(len(years) * 0.6)) :]
    last_train = panel[panel["year"] < test_years[-1]] if test_years else panel

    logger.info("Fitting final_tree (identical hyperparameters to goal2)")
    final_tree = HistGradientBoostingRegressor(
        max_iter=200, max_depth=4, learning_rate=0.05, l2_regularization=1.0, random_state=0
    )
    final_tree.fit(last_train[ALL_COLS], last_train["fwd_ret"])

    sample = last_train.sample(n=min(5000, len(last_train)), random_state=0)
    pi = permutation_importance(final_tree, sample[ALL_COLS], sample["fwd_ret"], n_repeats=3, random_state=0, n_jobs=-1)
    order = np.argsort(-pi.importances_mean)
    top_idx = order[:15]
    top_cols = [ALL_COLS[i] for i in top_idx]
    print("\n=== Top 15 features by permutation importance (re-derived, should match goal2's top-20) ===")
    for rank, i in enumerate(top_idx, 1):
        print(f"{rank:3d} {ALL_COLS[i]:24s} {PILLAR_OF.get(ALL_COLS[i], '?'):24s} {pi.importances_mean[i]:.5f}")

    logger.info(f"Computing 2D partial dependence for {len(top_cols) * (len(top_cols) - 1) // 2} pairs among top 15")
    pd_sample = last_train.sample(n=min(3000, len(last_train)), random_state=1)
    grid_res = 8
    pd_1d = {}
    for c in top_cols:
        r = partial_dependence(
            final_tree, pd_sample[ALL_COLS], features=[ALL_COLS.index(c)], grid_resolution=grid_res, kind="average"
        )
        pd_1d[c] = r

    interaction_scores = []
    for i, ca in enumerate(top_cols):
        for cb in top_cols[i + 1 :]:
            fa, fb = ALL_COLS.index(ca), ALL_COLS.index(cb)
            r2d = partial_dependence(
                final_tree, pd_sample[ALL_COLS], features=[(fa, fb)], grid_resolution=grid_res, kind="average"
            )
            surf = r2d["average"][0]  # shape (grid_res, grid_res)
            row_means = surf.mean(axis=1, keepdims=True)
            col_means = surf.mean(axis=0, keepdims=True)
            grand_mean = surf.mean()
            additive = row_means + col_means - grand_mean
            deviation = surf - additive
            h_like = np.sqrt((deviation**2).mean())
            interaction_scores.append((h_like, ca, cb))

    interaction_scores.sort(reverse=True)
    print("\n=== Top 15 candidate interaction pairs by 2D partial-dependence deviation (H-stat-like) ===")
    for rank, (score, ca, cb) in enumerate(interaction_scores[:15], 1):
        print(f"{rank:3d} {ca:20s} x {cb:20s} deviation={score:.6f}")

    value_risk_pairs = {
        ("pe", "vol_60d"),
        ("pb", "vol_60d"),
        ("ps", "vol_60d"),
        ("pe", "vol_252d"),
        ("pb", "vol_252d"),
        ("ps", "vol_252d"),
    }
    ranked_pairs = [(ca, cb) for _, ca, cb in interaction_scores]
    vr_ranks = [
        i + 1 for i, (ca, cb) in enumerate(ranked_pairs) if (ca, cb) in value_risk_pairs or (cb, ca) in value_risk_pairs
    ]
    print(
        f"\nValue x Risk pairs (already-live interaction) rank among these {len(ranked_pairs)} candidate pairs: {vr_ranks or 'not in top-15-feature set at all'}"
    )

    print("\n=== Fama-MacBeth main-effect + interaction test for top 5 candidate pairs ===")
    for score, ca, cb in interaction_scores[:5]:
        if ca not in panel_raw.columns or cb not in panel_raw.columns:
            print(f"{ca} x {cb}: SKIPPED (not in raw panel - engineered/derived col not directly testable)")
            continue
        res = fama_macbeth_interaction(panel_raw, ca, cb)
        print(f"\n{ca} x {cb} (tree deviation={score:.6f}):")
        for label, r in (("FULL", res["full"]), ("ERA1", res["era1"]), ("ERA2", res["era2"])):
            if r is None:
                print(f"  {label}: insufficient months")
                continue
            print(
                f"  {label} (n_months={r['n_months']}): "
                f"t_a={r['t'][1]:.2f} t_b={r['t'][2]:.2f} t_interaction={r['t'][3]:.2f} "
                f"coef_interaction={r['coef'][3]:.5f}"
            )


if __name__ == "__main__":
    main()
