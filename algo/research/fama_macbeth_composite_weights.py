#!/usr/bin/env python3
"""
Fama-MacBeth test of the TOP-LEVEL composite_score combination (Quality/Growth/Value/Risk/
Momentum/Size pillar weights).

Built 2026-08-25, REBUILT 2026-08-27 (goal: user goal-mode session found this script's proxies
had drifted stale against the pillar formulas that shipped on 2026-08-27 - Growth collapsed from
a 14-input blend to a single book_value_growth input, Quality's components changed (ROCE/FCF
Margin/margin_volatility/asset_turnover/gross_profitability replacing interest_coverage/payout),
Value dropped dividend_yield for net_payout_yield and added PEG/margin_of_safety, Positioning was
fully retired as a scored pillar, and Size was promoted from a Value sub-component to a real
top-level pillar. This rewrite re-derives every proxy from the CURRENT live formula in
loaders/load_stock_scores.py, drops positioning_proxy entirely (nothing left to test - retired on
its own evidence), and folds size_proxy into the core 6-pillar regression instead of treating it
as an optional 7th-factor add-on (that question was already answered and acted on).

SECOND, more important change this pass (user pushback: "our analysis is no good with partial
data... we cannot tell proper relationships between things"): the 2026-08-25
"PARTIAL-AVAILABILITY REDESIGN" that z-scores each pillar over whatever's available and then
0-imputes ("no information") any missing pillar to grow the sample from ~850 to ~6,500 symbols
is a real methodological risk the user is right to flag - missingness is not necessarily random
(MNAR): a stock missing Quality data because it's a thin SEC filer is a DIFFERENT population, not
an "average" one, and imputing it to 0 can manufacture or mask a cross-pillar relationship rather
than reveal a real one. This script now runs BOTH regimes side by side on every check
(multivariate, univariate, half-split) - COMPLETE-CASE (strict dropna, every pillar proxy must be
genuinely observed that symbol-month, small biased-toward-large-caps sample but no imputation
artifact) and PARTIAL-AVAILABILITY (the larger, imputed sample) - and flags disagreement rather
than trusting either alone. A pillar weight is only treated as evidence-backed here if the
finding is directionally consistent across BOTH regimes AND both half-split eras - the same
"don't trust a single point estimate" discipline this project already applies elsewhere
(margin_volatility_3y, Size's promotion), extended to the imputation question specifically.

Pillar proxies (z-scored components combined at each pillar's LIVE weight ratios - NOT
independently re-derived per-component weights, since that's what the per-pillar scripts already
tested; this script answers the separate top-level question), verified against
loaders/load_stock_scores.py directly on 2026-08-27:
- growth_proxy: single input, -book_value_growth (BVPS YoY %, inverted - lower is better, same
  sign the live _score_growth curve uses). Sole survivor of an isolated-FM audit that found the
  old 11/14-input blend's other candidates all dominated/subsumed by this one - see
  loaders/load_stock_scores.py's _score_growth docstring for the full evidence trail.
- quality_proxy: ROE 11% + ROA 18% + ROCE 18% + FCF Margin 15% + (-Debt/Equity) 18% +
  (-Margin Volatility 3Y) 7% + Asset Turnover 7% + Gross Profitability 7% (nominal 101, matches
  _score_quality's current 8-component live weights exactly - Altman Z excluded, computed/
  persisted but deliberately unscored as a discrete distress classifier, not part of the live
  weighted formula either).
- value_proxy: PE/PB/PS/FCF-yield only, renormalized over the live PE12/PB30/PS27/FCF9=78 nominal
  (excludes PEG7/NetPayoutYield8/MoS7=22 of the live 100 - PEG needs a growth cross-term,
  margin-of-safety needs a full DCF model, net_payout_yield needs buyback data not in this
  script's point-in-time fundamentals fetch; none is a single point-in-time ratio like the rest
  of this panel, same limitation the pre-2026-08-27 version of this script already had and
  disclosed - NOT a new gap, still an honest ~78%-of-live-weight proxy, not the full formula).
  No embedded Size term (unlike the pre-2026-08-27 version) - Size is a real top-level pillar now,
  not a Value sub-component.
- stability_proxy (maps to live BASE_PILLAR_WEIGHTS["risk"]): (-vol_60d)*0.45 + (-|beta-1|)*0.20 +
  (-downside_vol_60d)*0.15 + max_dd*0.20 - unchanged, still matches the live Risk formula.
- momentum_proxy: mom_3m*0.20 + mom_12_1*0.35 + rsi_14*0.21 + macd_sign*0.16 +
  avg(price_vs_sma_50,price_vs_sma_200)*0.08 - unchanged, still matches _score_momentum live.
- size_proxy: -log10(market_cap) - now a REAL top-level pillar (BASE_PILLAR_WEIGHTS["size"]=0.20
  as of the 2026-08-27 re-promotion), not an optional 7th-factor test. positioning_proxy REMOVED
  entirely - Positioning has no live scoring weight to validate any more (fully retired
  2026-08-27, A/D rating null across every methodology tried including a full 2000-2026 re-test).

Each raw component is winsorized/z-scored the same way as its origin script BEFORE being combined
into the pillar proxy, then the resulting pillar proxies are z-scored AGAIN at the top level
before the final regression - so the final coefficients are directly comparable "how much does a
1-std move in this whole pillar's current formula predict forward return, controlling for the
others" numbers.

Usage:
    python -m algo.research.fama_macbeth_composite_weights [options]
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Lasso, Ridge

from algo.research.fama_macbeth_momentum_factors import (
    build_month_end_panel,
    compute_daily_indicators,
)
from algo.research.fama_macbeth_momentum_factors import (
    fetch_daily_prices as fetch_daily_close,
)
from algo.research.fama_macbeth_price_factors import (
    _fama_macbeth,
    _trailing_cumret,
    fetch_month_end_prices,
)
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.fama_macbeth_value_factors import fetch_annual_value_fundamentals
from algo.research.growth_reinvestment_book_value_candidates import (
    build_panel as build_book_value_panel,
)
from algo.research.growth_reinvestment_book_value_candidates import (
    fetch_panel_raw as fetch_book_value_fundamentals,
)
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)

# 6 pillars, matching loaders/load_stock_scores.py's CURRENT BASE_PILLAR_WEIGHTS keys exactly
# (quality/growth/value/risk/momentum/size) - no positioning_proxy (retired, nothing to test).
PILLAR_COLS = ["growth_proxy", "value_proxy", "quality_proxy", "stability_proxy", "momentum_proxy", "size_proxy"]

PILLAR_TO_LIVE_KEY = {
    "growth_proxy": "growth",
    "value_proxy": "value",
    "quality_proxy": "quality",
    "stability_proxy": "risk",
    "momentum_proxy": "momentum",
    "size_proxy": "size",
}


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def build_value_panel_raw() -> pd.DataFrame:
    fund = fetch_annual_value_fundamentals()
    shares = fund["shares_diluted"]
    out = fund[["symbol", "fiscal_year"]].copy()
    out["eps"] = fund["eps"]
    out["book_value_per_share"] = fund["stockholders_equity"] / shares
    out["sales_per_share"] = fund["revenue"] / shares
    out["fcf_per_share"] = fund["free_cash_flow"] / shares
    out["shares_diluted"] = shares
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


from algo.research.fama_macbeth_growth_factors import REPORTING_LAG_DAYS, merge_asof_monthly  # noqa: E402


def run(start_date: str, end_date: str, min_cross_section: int) -> None:  # noqa: C901 -- research script
    logger.info("Building fundamentals panels (growth/value/quality)")
    growth_fund = build_book_value_panel(fetch_book_value_fundamentals())
    value_fund = build_value_panel_raw()
    quality_raw = fetch_annual_quality_fundamentals()
    quality_fund = build_quality_panel(quality_raw)
    # asset_turnover isn't built by build_quality_panel() (added to _score_quality later than
    # that panel builder was last touched) - Revenue/Total Assets, same DuPont formula as
    # quality_asset_turnover_piotroski_candidates.py.
    quality_fund = quality_fund.merge(
        quality_raw[["symbol", "fiscal_year", "revenue", "total_assets"]], on=["symbol", "fiscal_year"], how="left"
    )
    quality_fund["asset_turnover"] = np.where(
        quality_fund["total_assets"] > 0, quality_fund["revenue"] / quality_fund["total_assets"], np.nan
    )

    logger.info("Fetching price panel + momentum/stability indicators")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    ret = px.pct_change(fill_method=None)
    mkt = ret["SPY"]
    months = px.index
    months_period = pd.PeriodIndex(months, freq="M")

    daily_close = fetch_daily_close(start_date, end_date)
    daily_close = compute_daily_indicators(daily_close)
    _px_daily, indicators = build_month_end_panel(daily_close)
    for key in indicators:
        indicators[key] = (
            indicators[key].set_axis(pd.PeriodIndex(indicators[key].index, freq="M")).reindex(months_period)
        )

    growth_monthly = merge_asof_monthly(months, growth_fund, cols=["book_value_growth"])
    value_monthly = merge_asof_monthly(
        months, value_fund, cols=["eps", "book_value_per_share", "sales_per_share", "fcf_per_share", "shares_diluted"]
    )
    quality_monthly = merge_asof_monthly(
        months,
        quality_fund,
        cols=[
            "roe",
            "roa",
            "roce",
            "fcf_margin",
            "debt_to_equity",
            "margin_volatility_3y",
            "asset_turnover",
            "gross_profitability",
        ],
    )

    beta_window = 24
    vol_window = 12
    # Two parallel record sets: "partial" (0-imputed, matches the live composite's own
    # skip-unavailable/renormalize tolerance) and "complete" (strict dropna on the 6 raw pillar
    # proxies BEFORE any imputation - a real "is this relationship there even without imputation
    # help" check, per the user's concern this pass exists to address).
    records_partial: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    records_complete: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    for i in range(beta_window, len(months) - 1):
        month = months[i]

        g = growth_monthly.get(month)
        v = value_monthly.get(month)
        q = quality_monthly.get(month)
        if g is None or v is None or q is None or g.empty or v.empty or q.empty:
            continue

        growth_proxy = -_zwinsor(g["book_value_growth"])

        price = px.iloc[i].reindex(v.index)
        pe = np.where(v["eps"] > 0, price / v["eps"], np.nan)
        pb = np.where(v["book_value_per_share"] > 0, price / v["book_value_per_share"], np.nan)
        ps = np.where(v["sales_per_share"] > 0, price / v["sales_per_share"], np.nan)
        fcf_yield = v["fcf_per_share"] / price
        # value_proxy: PE12/PB30/PS27/FCF9 renormalized over 78 (live's remaining 22 - PEG7/
        # NetPayoutYield8/MoS7 - excluded, see module docstring). No Size term (Size is now a
        # separate top-level pillar, not a Value sub-component).
        value_proxy = (
            (12.0 / 78.0) * _zwinsor(-pd.Series(pe, index=v.index))
            + (30.0 / 78.0) * _zwinsor(-pd.Series(pb, index=v.index))
            + (27.0 / 78.0) * _zwinsor(-pd.Series(ps, index=v.index))
            + (9.0 / 78.0) * _zwinsor(fcf_yield)
        )

        market_cap = price * v["shares_diluted"]
        log_mc = np.where((market_cap >= 1e6) & (market_cap <= 1e13), np.log10(market_cap), np.nan)
        size_proxy = _zwinsor(-pd.Series(log_mc, index=v.index))

        # quality_proxy: ROE11/ROA18/ROCE18/FCFmargin15/(-D2E)18/(-marginvol)7/assetturnover7/
        # grossprofitability7, nominal 101 - matches _score_quality's current 8-component live
        # weights exactly.
        quality_proxy = (
            (11.0 / 101.0) * _zwinsor(q["roe"])
            + (18.0 / 101.0) * _zwinsor(q["roa"])
            + (18.0 / 101.0) * _zwinsor(q["roce"])
            + (15.0 / 101.0) * _zwinsor(q["fcf_margin"])
            + (18.0 / 101.0) * _zwinsor(-q["debt_to_equity"])
            + (7.0 / 101.0) * _zwinsor(-q["margin_volatility_3y"])
            + (7.0 / 101.0) * _zwinsor(q["asset_turnover"])
            + (7.0 / 101.0) * _zwinsor(q["gross_profitability"])
        )

        win = ret.iloc[i - vol_window + 1 : i + 1]
        vol = win.std() * np.sqrt(12)
        downside_vol = win.where(win < 0).std() * np.sqrt(12)
        winb = ret.iloc[i - beta_window + 1 : i + 1]
        mkt_win = mkt.iloc[i - beta_window + 1 : i + 1]
        mkt_var = mkt_win.var()
        beta = (
            winb.apply(lambda col, m=mkt_win: col.cov(m)) / mkt_var
            if mkt_var and mkt_var > 0
            else pd.Series(np.nan, index=winb.columns)
        )
        win_px = px.iloc[i - vol_window + 1 : i + 1]
        max_dd = (win_px / win_px.cummax() - 1.0).min()
        stability_proxy = (
            0.45 * _zwinsor(-vol)
            + 0.20 * _zwinsor(-(beta - 1.0).abs())
            + 0.15 * _zwinsor(-downside_vol)
            + 0.20 * _zwinsor(max_dd)
        )

        mom_3m = _trailing_cumret(px, i, 3)
        mom_12_1 = _trailing_cumret(px, i - 1, 11)
        rsi = indicators["rsi_14"].iloc[i]
        macd_sign = indicators["macd_sign"].iloc[i]
        sma_avg = (indicators["price_vs_sma_50"].iloc[i] + indicators["price_vs_sma_200"].iloc[i]) / 2.0
        momentum_proxy = (
            0.20 * _zwinsor(mom_3m)
            + 0.35 * _zwinsor(mom_12_1)
            + 0.21 * _zwinsor(rsi)
            + 0.16 * _zwinsor(macd_sign)
            + 0.08 * _zwinsor(sma_avg)
        )

        fwd_ret = ret.iloc[i + 1]

        raw = pd.DataFrame(
            {
                "growth_proxy": growth_proxy,
                "value_proxy": value_proxy,
                "quality_proxy": quality_proxy,
                "stability_proxy": stability_proxy,
                "momentum_proxy": momentum_proxy,
                "size_proxy": size_proxy,
                "fwd_ret": fwd_ret,
            }
        )
        raw = raw.replace([np.inf, -np.inf], np.nan)
        raw = raw.dropna(subset=["fwd_ret"])
        raw = raw[(raw["fwd_ret"] > -0.95) & (raw["fwd_ret"] < 5.0)]
        if len(raw) < min_cross_section:
            continue

        # COMPLETE-CASE: strict dropna on the 6 raw pillar proxies (pre-imputation) - only
        # symbol-months where every pillar was genuinely observed. Z-score within THIS reduced
        # universe (not reusing partial's z-scores) so the comparison is apples-to-apples.
        complete = raw.dropna(subset=PILLAR_COLS)
        if len(complete) >= min_cross_section:
            complete = complete.copy()
            for col in PILLAR_COLS:
                complete[col] = _zwinsor(complete[col])
            records_complete.append((month, complete))

        # PARTIAL-AVAILABILITY: z-score each pillar over whatever's available this month, then
        # 0-impute missing (matches the live composite_score's own tolerance).
        partial = raw.copy()
        for col in PILLAR_COLS:
            partial[col] = _zwinsor(partial[col]).fillna(0.0)
        records_partial.append((month, partial))

    if not records_partial:
        raise RuntimeError("No usable cross-sectional months - pillars may not overlap enough symbols")
    if not records_complete:
        logger.warning("No complete-case months cleared min_cross_section - skipping that comparison")

    def _report(records: list[tuple[pd.Timestamp, pd.DataFrame]], label: str) -> None:
        sizes = [len(f) for _, f in records]
        print(f"\n########## {label} ##########")
        print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
        print(f"Median cross-section size: {int(np.median(sizes))}\n")

        pooled = pd.concat([f for _, f in records], ignore_index=True)
        print("=== Pooled pillar-proxy pairwise correlations (multicollinearity diagnostic) ===")
        print(pooled[PILLAR_COLS].corr().round(2).to_string())

        print(f"\n=== Multivariate Fama-MacBeth: {label} ===")
        print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
        multi = _fama_macbeth(records, PILLAR_COLS)
        for name, (mean, t) in multi.items():
            print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(records):9d}")

        print(f"\n=== Univariate Fama-MacBeth: {label} ===")
        print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s}")
        for c in PILLAR_COLS:
            uni = _fama_macbeth(records, [c])
            mean, t = uni[c]
            print(f"{c:18s} {mean:10.5f} {t:8.2f}")

        split_idx = len(records) // 2
        first_half, second_half = records[:split_idx], records[split_idx:]
        for half_label, half in (
            (f"FIRST HALF ({first_half[0][0]} to {first_half[-1][0]})", first_half),
            (f"SECOND HALF ({second_half[0][0]} to {second_half[-1][0]})", second_half),
        ):
            if not half:
                continue
            print(f"\n=== Half-split robustness ({label}), {half_label} ===")
            print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
            half_multi = _fama_macbeth(half, PILLAR_COLS)
            for name, (mean, t) in half_multi.items():
                print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(half):9d}")

    _report(records_partial, "PARTIAL-AVAILABILITY (0-imputed missing pillars, larger sample)")
    if records_complete:
        _report(records_complete, "COMPLETE-CASE (strict dropna, no imputation, smaller sample)")

        # DIRECT AGREEMENT CHECK - the actual answer to the user's concern: does each pillar's
        # multivariate sign/significance survive BOTH regimes, or does it only show up once
        # imputation manufactures extra sample?
        multi_partial = _fama_macbeth(records_partial, PILLAR_COLS)
        multi_complete = _fama_macbeth(records_complete, PILLAR_COLS)
        print("\n########## AGREEMENT CHECK: partial-availability vs complete-case ##########")
        print(f"{'pillar':18s} {'t_partial':>10s} {'t_complete':>11s} {'agree?':>8s}")
        for c in PILLAR_COLS:
            t_p = multi_partial[c][1]
            t_c = multi_complete[c][1]
            same_sign = (t_p > 0) == (t_c > 0)
            both_sig = abs(t_p) > 2.0 and abs(t_c) > 2.0
            verdict = "ROBUST" if (same_sign and both_sig) else ("same-sign" if same_sign else "DISAGREE")
            print(f"{c:18s} {t_p:10.2f} {t_c:11.2f} {verdict:>8s}")
        print(
            "\nOnly a pillar marked ROBUST here (significant AND same-signed in both the imputed"
            " and the strict-complete-case regime) should be treated as evidence for a"
            " BASE_PILLAR_WEIGHTS change. 'same-sign'-only or DISAGREE means the imputed sample's"
            " larger size is likely doing the work, not a real relationship - do not act on it"
            " without first checking whether missingness itself correlates with the outcome"
            " (survivorship/thin-filer bias) rather than assuming MCAR."
        )
    else:
        print("\n(No complete-case comparison available - see warning above.)")

    live_weights = " ".join(f"{k}={v}" for k, v in BASE_PILLAR_WEIGHTS.items())
    print(f"\nCurrent live BASE_PILLAR_WEIGHTS: {live_weights}")

    print("\n=== ML vs LIVE-LINEAR composite: walk-forward OOS head-to-head (partial-availability sample) ===")
    panel_rows = []
    for month, frame in records_partial:
        f = frame.copy()
        f["month"] = month
        panel_rows.append(f)
    panel = pd.concat(panel_rows, ignore_index=True)
    panel["year"] = pd.to_datetime(panel["month"]).dt.year
    years = sorted(panel["year"].unique())
    first_test_idx = max(1, int(len(years) * 0.6))
    test_years = years[first_test_idx:]

    live_weight_map = {c: BASE_PILLAR_WEIGHTS[k] for c, k in PILLAR_TO_LIVE_KEY.items()}

    ridge_alphas = [1.0, 10.0, 100.0]
    lasso_alphas = [1e-5, 1e-4, 1e-3, 1e-2]
    model_preds: dict[str, list[float]] = {
        "ml_tree(d4,l2=1)": [],
        **{f"ridge_a{a:g}": [] for a in ridge_alphas},
        **{f"lasso_a{a:g}": [] for a in lasso_alphas},
    }
    lasso_coefs: dict[float, list[np.ndarray[Any, Any]]] = {a: [] for a in lasso_alphas}
    live_pred, actual = [], []

    for test_year in test_years:
        train = panel[panel["year"] < test_year]
        test = panel[panel["year"] == test_year]
        if train.empty or len(test) < min_cross_section:
            continue
        x_train, y_train = train[PILLAR_COLS], train["fwd_ret"]
        x_test = test[PILLAR_COLS]

        tree = HistGradientBoostingRegressor(
            max_iter=200, max_depth=4, learning_rate=0.05, l2_regularization=1.0, random_state=0
        )
        tree.fit(x_train, y_train)
        model_preds["ml_tree(d4,l2=1)"].extend(tree.predict(x_test).tolist())

        for a in ridge_alphas:
            ridge = Ridge(alpha=a)
            ridge.fit(x_train, y_train)
            model_preds[f"ridge_a{a:g}"].extend(ridge.predict(x_test).tolist())

        for a in lasso_alphas:
            lasso = Lasso(alpha=a, max_iter=5000)
            lasso.fit(x_train, y_train)
            model_preds[f"lasso_a{a:g}"].extend(lasso.predict(x_test).tolist())
            lasso_coefs[a].append(lasso.coef_.copy())

        live_linear = sum(test[c] * w for c, w in live_weight_map.items())
        live_pred.extend(live_linear.tolist())
        actual.extend(test["fwd_ret"].tolist())
        logger.info(f"{test_year}: train_rows={len(train)} test_rows={len(test)} done")

    if live_pred:
        live_s = pd.Series(live_pred)
        act_s = pd.Series(actual)
        print(f"OOS symbol-months: {len(live_pred)}, test years: {test_years}")
        print(f"{'method':30s} {'Spearman':>10s} {'Pearson':>10s}")
        print(
            f"{'live_linear_fixed_pct':30s} {live_s.corr(act_s, method='spearman'):10.4f} {live_s.corr(act_s, method='pearson'):10.4f}"
        )
        for name, preds in model_preds.items():
            s = pd.Series(preds)
            print(f"{name:30s} {s.corr(act_s, method='spearman'):10.4f} {s.corr(act_s, method='pearson'):10.4f}")
        print("\n=== Lasso: which pillars got zeroed out (>50% of walk-forward folds)? ===")
        for a in lasso_alphas:
            coefs = np.array(lasso_coefs[a])
            zero_frac = (coefs == 0).mean(axis=0)
            zeroed = [PILLAR_COLS[i] for i in range(len(PILLAR_COLS)) if zero_frac[i] > 0.5]
            kept = [PILLAR_COLS[i] for i in range(len(PILLAR_COLS)) if zero_frac[i] <= 0.5]
            print(f"alpha={a:g}: zeroed={zeroed or 'none'}  kept={kept}")
    else:
        print("No usable walk-forward test years - min_cross_section too high?")


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
