#!/usr/bin/env python3
"""
Fama-MacBeth test of the TOP-LEVEL composite_score combination (Quality/Growth/Value/
Positioning/Stability/Momentum pillar weights).

Built 2026-08-25 (goal: figure out the right weightings for the FULL combined score, not just
each pillar in isolation). loaders/load_stock_scores.py's `base_weights` (quality=0.25,
growth=0.12, value=0.20, positioning=0.14, stability=0.14, momentum=0.15) have NO documented
empirical basis anywhere in the file - just a comment explaining the no-redistribution rule,
nothing about where the specific percentages came from. Grinold & Kahn's "Active Portfolio
Management" (the standard practitioner reference for combining multiple alpha signals) treats
this as a regression/IC-weighting problem: combine signals in proportion to their REALIZED
predictive power controlling for correlation among them - exactly what a multivariate
Fama-MacBeth regression does, which is why this script builds one pillar-level proxy per
pillar (using only the components each pillar-specific fama_macbeth_*.py script in this
directory found to carry real signal, or the live formula where nothing better is known yet)
and regresses forward return on all 6 jointly.

Pillar proxies (z-scored components combined at each pillar's LIVE weight ratios - NOT
independently re-derived per-component weights, since that's what the per-pillar scripts
already tested; this script answers the separate top-level question):
- growth_proxy: eps_growth_1y*0.45 + (-asset_growth_yoy)*0.25 + revenue_growth_1y*0.15 +
  sustainable_growth_rate*0.15 (matches _score_growth's live weights)
- value_proxy: -pe*0.18 -pb*0.20 -ps*0.18 + fcf_yield*0.10 + dividend_yield*0.02 -ev_ebitda*0.08
  -ev_revenue*0.08 (matches _score_value's live weights; PEG/margin-of-safety excluded, not
  computed here)
- quality_proxy: simple average of roe/roa/operating_margin/net_margin/(-debt_to_assets)/
  interest_coverage (matches the upstream equal-weighted-6 formula)
- stability_proxy: (-vol_60d)*0.45 + (-|beta-1|)*0.20 + (-downside_vol_60d)*0.15 + max_dd*0.20
  (matches this session's ALREADY-SHIPPED stability reweight)
- momentum_proxy: mom_3m*0.20 + mom_6m*0.20 + mom_12m*0.15 + rsi_14*0.21 + macd_sign*0.16 +
  avg(price_vs_sma_50,price_vs_sma_200)*0.08 (matches _score_momentum's live weights)
- positioning_proxy: ad_rating only (institutional_ownership/short_interest confirmed
  untestable - see fama_macbeth_positioning_ad_rating_null memory)

Each raw component is winsorized/z-scored the same way as its origin script BEFORE being
combined into the pillar proxy (so no single outlier component dominates the weighted sum),
then the resulting 6 pillar proxies are z-scored AGAIN at the top level before the final
regression - so the final coefficients are directly comparable "how much does a 1-std move in
this whole pillar's current formula predict forward return, controlling for the other 5
pillars" numbers.

Usage:
    python -m algo.research.fama_macbeth_composite_weights [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import (
    REPORTING_LAG_DAYS,
    fetch_annual_fundamentals,
    merge_asof_monthly,
)
from algo.research.fama_macbeth_momentum_factors import (
    build_month_end_panel,
    compute_daily_indicators,
)
from algo.research.fama_macbeth_momentum_factors import (
    fetch_daily_prices as fetch_daily_close,
)
from algo.research.fama_macbeth_positioning_factors import (
    compute_ad_rating_series,
    fetch_daily_ohlcv,
)
from algo.research.fama_macbeth_price_factors import (
    _fama_macbeth,
    _trailing_cumret,
    fetch_month_end_prices,
)
from algo.research.fama_macbeth_quality_factors import fetch_annual_quality_fundamentals
from algo.research.fama_macbeth_value_factors import fetch_annual_value_fundamentals

logger = logging.getLogger(__name__)

PILLAR_COLS = ["growth_proxy", "value_proxy", "quality_proxy", "stability_proxy", "momentum_proxy", "positioning_proxy"]

# ADDED 2026-08-25 (goal: real-money-readiness follow-up) to answer a specific open question:
# does log(market_cap) (the Size factor, t=-5.37 standalone per
# stock_scores_size_factor_missing_and_composite_weights_tested_20260825) retain independent
# significance when controlling for ALL SIX existing pillar proxies jointly, not just alone?
# If yes, that's real evidence Size carries information the other 6 pillars don't already
# capture between them - the right bar for "does this deserve its own top-level composite
# slot" per Grinold & Kahn's IC-weighting framework, same standard this whole script applies
# to the other 6. Kept as a strict ADDITION to PILLAR_COLS (SEVEN_COL) rather than folded into
# the six above, so the original 6-pillar run this script already produced stays reproducible
# unchanged - this augments it, doesn't replace it.
SEVEN_COLS = [*PILLAR_COLS, "size_proxy"]


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def build_growth_and_sgr_panel() -> pd.DataFrame:
    fund = fetch_annual_fundamentals()
    fund = fund.sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)
    g = fund.groupby("symbol", group_keys=False)

    def growth(col: str, n: int = 1) -> pd.Series:
        prior = g[col].shift(n)
        valid = (prior > 0) & (fund[col] > 0)
        out = pd.Series(np.nan, index=fund.index)
        out[valid] = (fund[col][valid] / prior[valid]) ** (1.0 / n) - 1.0
        return out

    out = fund[["symbol", "fiscal_year"]].copy()
    out["eps_growth_1y"] = growth("eps")
    out["revenue_growth_1y"] = growth("revenue")
    out["asset_growth_yoy"] = growth("total_assets")
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def build_sgr_panel() -> pd.DataFrame:
    """Sustainable growth rate = ROE * retention ratio, from quality+value fundamentals."""
    q = fetch_annual_quality_fundamentals()
    v = fetch_annual_value_fundamentals()
    merged = q.merge(v[["symbol", "fiscal_year", "dividends_paid"]], on=["symbol", "fiscal_year"], how="left")
    roe = np.where(merged["stockholders_equity"] > 0, merged["net_income"] / merged["stockholders_equity"], np.nan)
    retention = np.where(merged["net_income"] > 0, 1.0 - merged["dividends_paid"].abs() / merged["net_income"], np.nan)
    out = merged[["symbol", "fiscal_year"]].copy()
    out["sustainable_growth_rate"] = roe * retention
    out["known_date"] = pd.to_datetime(merged["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def build_value_panel_raw() -> pd.DataFrame:
    fund = fetch_annual_value_fundamentals()
    shares = fund["shares_diluted"]
    ebitda = fund["operating_income"] + fund["depreciation_expense"] + fund["amortization_expense"]
    net_debt = (
        fund["long_term_debt"].fillna(0) + fund["short_term_debt"].fillna(0) - fund["cash_and_equivalents"].fillna(0)
    )
    out = fund[["symbol", "fiscal_year"]].copy()
    out["eps"] = fund["eps"]
    out["book_value_per_share"] = fund["stockholders_equity"] / shares
    out["sales_per_share"] = fund["revenue"] / shares
    out["fcf_per_share"] = fund["free_cash_flow"] / shares
    out["dividend_per_share"] = fund["dividends_paid"].abs() / shares
    out["ebitda_per_share"] = ebitda / shares
    out["net_debt_per_share"] = net_debt / shares
    out["shares_diluted"] = shares  # for size_proxy (market_cap = price * shares_diluted below)
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def build_quality_panel_raw() -> pd.DataFrame:
    fund = fetch_annual_quality_fundamentals()
    out = fund[["symbol", "fiscal_year"]].copy()
    out["roe"] = np.where(fund["stockholders_equity"] > 0, fund["net_income"] / fund["stockholders_equity"], np.nan)
    out["roa"] = np.where(fund["total_assets"] > 0, fund["net_income"] / fund["total_assets"], np.nan)
    out["operating_margin"] = np.where(fund["revenue"] > 0, fund["operating_income"] / fund["revenue"], np.nan)
    out["net_margin"] = np.where(fund["revenue"] > 0, fund["net_income"] / fund["revenue"], np.nan)
    total_debt = fund["long_term_debt"].fillna(0) + fund["short_term_debt"].fillna(0)
    out["debt_to_assets"] = np.where(fund["total_assets"] > 0, total_debt / fund["total_assets"], np.nan)
    out["interest_coverage"] = np.where(
        fund["interest_expense"] > 0, fund["operating_income"] / fund["interest_expense"], np.nan
    )
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Building fundamentals panels (growth/value/quality/SGR)")
    growth_fund = build_growth_and_sgr_panel()
    sgr_fund = build_sgr_panel()
    value_fund = build_value_panel_raw()
    quality_fund = build_quality_panel_raw()

    logger.info("Fetching price panel + momentum/stability indicators")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    ret = px.pct_change(fill_method=None)
    mkt = ret["SPY"]
    months = px.index

    # NOTE: indicators/ad_panel are built from independent daily pulls, so their own month
    # indices can differ in dtype (datetime64[M] vs px's plain `date` objects) and coverage
    # from px's `months`. Reindex everything to px's own month sequence (by calendar-month
    # label, via PeriodIndex, which is dtype-agnostic) before any positional .iloc[i] access -
    # mixing dtypes here previously caused a silent "month in ad_panel.index" false-negative
    # that made positioning_proxy always empty and killed every cross-section.
    months_period = pd.PeriodIndex(months, freq="M")

    daily_close = fetch_daily_close(start_date, end_date)
    daily_close = compute_daily_indicators(daily_close)
    _px_daily, indicators = build_month_end_panel(daily_close)
    for key in indicators:
        indicators[key] = (
            indicators[key].set_axis(pd.PeriodIndex(indicators[key].index, freq="M")).reindex(months_period)
        )

    daily_ohlcv = fetch_daily_ohlcv(start_date, end_date)
    ad_rating = compute_ad_rating_series(daily_ohlcv)
    daily_ohlcv = daily_ohlcv.set_index(["symbol", "date"])
    daily_ohlcv["ad_rating"] = ad_rating
    daily_ohlcv = daily_ohlcv.reset_index()
    daily_ohlcv["month"] = daily_ohlcv["date"].values.astype("datetime64[M]")
    ad_monthly = daily_ohlcv.sort_values("date").groupby(["symbol", "month"], as_index=False).last()
    ad_panel = ad_monthly.pivot(index="month", columns="symbol", values="ad_rating").sort_index()
    ad_panel = ad_panel.set_axis(pd.PeriodIndex(ad_panel.index, freq="M")).reindex(months_period)

    growth_monthly = merge_asof_monthly(
        months, growth_fund, cols=["eps_growth_1y", "revenue_growth_1y", "asset_growth_yoy"]
    )
    sgr_monthly = merge_asof_monthly(months, sgr_fund, cols=["sustainable_growth_rate"])
    value_monthly = merge_asof_monthly(
        months,
        value_fund,
        cols=[
            "eps",
            "book_value_per_share",
            "sales_per_share",
            "fcf_per_share",
            "dividend_per_share",
            "ebitda_per_share",
            "net_debt_per_share",
            "shares_diluted",
        ],
    )
    quality_monthly = merge_asof_monthly(
        months,
        quality_fund,
        cols=["roe", "roa", "operating_margin", "net_margin", "debt_to_assets", "interest_coverage"],
    )

    beta_window = 24
    vol_window = 12
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    for i in range(beta_window, len(months) - 1):
        month = months[i]

        g = growth_monthly.get(month)
        s = sgr_monthly.get(month)
        v = value_monthly.get(month)
        q = quality_monthly.get(month)
        if g is None or s is None or v is None or q is None or g.empty or v.empty or q.empty:
            continue

        growth_proxy = (
            0.45 * _zwinsor(g["eps_growth_1y"])
            + 0.25 * _zwinsor(-g["asset_growth_yoy"])
            + 0.15 * _zwinsor(g["revenue_growth_1y"])
            + 0.15 * _zwinsor(s["sustainable_growth_rate"])
        )

        price = px.iloc[i].reindex(v.index)
        pe = np.where(v["eps"] > 0, price / v["eps"], np.nan)
        pb = np.where(v["book_value_per_share"] > 0, price / v["book_value_per_share"], np.nan)
        ps = np.where(v["sales_per_share"] > 0, price / v["sales_per_share"], np.nan)
        fcf_yield = v["fcf_per_share"] / price
        dividend_yield = v["dividend_per_share"] / price
        ev_per_share = price + v["net_debt_per_share"]
        ev_ebitda = np.where(v["ebitda_per_share"] > 0, ev_per_share / v["ebitda_per_share"], np.nan)
        ev_revenue = np.where(v["sales_per_share"] > 0, ev_per_share / v["sales_per_share"], np.nan)
        value_proxy = (
            0.18 * _zwinsor(-pd.Series(pe, index=v.index))
            + 0.20 * _zwinsor(-pd.Series(pb, index=v.index))
            + 0.18 * _zwinsor(-pd.Series(ps, index=v.index))
            + 0.10 * _zwinsor(fcf_yield)
            + 0.02 * _zwinsor(dividend_yield)
            + 0.08 * _zwinsor(-pd.Series(ev_ebitda, index=v.index))
            + 0.08 * _zwinsor(-pd.Series(ev_revenue, index=v.index))
        )

        quality_proxy = (
            _zwinsor(q["roe"])
            + _zwinsor(q["roa"])
            + _zwinsor(q["operating_margin"])
            + _zwinsor(q["net_margin"])
            + _zwinsor(-q["debt_to_assets"])
            + _zwinsor(q["interest_coverage"])
        ) / 6.0

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
        mom_6m = _trailing_cumret(px, i, 6)
        mom_12m = _trailing_cumret(px, i, 12)
        rsi = indicators["rsi_14"].iloc[i]
        macd_sign = indicators["macd_sign"].iloc[i]
        sma_avg = (indicators["price_vs_sma_50"].iloc[i] + indicators["price_vs_sma_200"].iloc[i]) / 2.0
        momentum_proxy = (
            0.20 * _zwinsor(mom_3m)
            + 0.20 * _zwinsor(mom_6m)
            + 0.15 * _zwinsor(mom_12m)
            + 0.21 * _zwinsor(rsi)
            + 0.16 * _zwinsor(macd_sign)
            + 0.08 * _zwinsor(sma_avg)
        )

        positioning_proxy = _zwinsor(ad_panel.iloc[i])

        # SIZE PROXY (added 2026-08-25, see SEVEN_COLS comment above): market_cap = price *
        # diluted shares outstanding, same point-in-time construction as the rest of this
        # panel (no look-ahead - shares_diluted comes from the same as-of fundamentals join as
        # every other value_monthly field). Oriented like every other proxy here (higher =
        # better/more bullish forward-return signal), so sign-flipped: -log(market_cap), since
        # smaller companies showed the positive forward-return premium (Banz 1981 / t=-5.37 on
        # raw log(market_cap) vs return, i.e. return falls as size rises).
        market_cap = price * v["shares_diluted"]
        size_proxy = _zwinsor(-np.log(market_cap.where(market_cap > 0)))

        fwd_ret = ret.iloc[i + 1]

        frame = pd.DataFrame(
            {
                "growth_proxy": growth_proxy,
                "value_proxy": value_proxy,
                "quality_proxy": quality_proxy,
                "stability_proxy": stability_proxy,
                "momentum_proxy": momentum_proxy,
                "positioning_proxy": positioning_proxy,
                "size_proxy": size_proxy,
                "fwd_ret": fwd_ret,
            }
        )
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue

        for col in SEVEN_COLS:
            frame[col] = _zwinsor(frame[col])

        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months - pillars may not overlap enough symbols")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("=== Multivariate Fama-MacBeth: TOP-LEVEL pillar combination (6 pillars) ===")
    print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, PILLAR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth (each pillar's current formula, alone) ===")
    print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s}")
    for c in PILLAR_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:18s} {mean:10.5f} {t:8.2f}")

    # ADDED 2026-08-25: does Size retain independent significance once it has to compete with
    # ALL 6 existing pillars in the SAME multivariate regression, on the SAME sample (the
    # 6-pillar run above re-run implicitly restricted to months/symbols with usable
    # shares_diluted, for a clean apples-to-apples comparison)?
    print("\n=== Multivariate Fama-MacBeth: TOP-LEVEL pillar combination + SIZE (7 factors) ===")
    print(f"{'pillar':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi7 = _fama_macbeth(records, SEVEN_COLS)
    for name, (mean, t) in multi7.items():
        print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth: SIZE alone (same sample as above) ===")
    uni_size = _fama_macbeth(records, ["size_proxy"])
    mean, t = uni_size["size_proxy"]
    print(f"{'size_proxy':18s} {mean:10.5f} {t:8.2f}")

    print(
        "\nCurrent live base_weights: quality=0.25 growth=0.12 value=0.20 positioning=0.14 stability=0.14 momentum=0.15"
        " (size_proxy has no top-level slot - it's a 20% sub-component inside value_proxy's live"
        " formula only, effective top-level weight ~4%)"
    )


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
