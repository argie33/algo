#!/usr/bin/env python3
"""
Tests two Quality candidates flagged as gaps 2026-08-27 (user-supplied literature checklist):

- roic_minus_wacc: economic-value-added spread (roic_pct - WACC), distinct from raw roic_pct
  (already tested, t=0.46, dead weight - see fama_macbeth_quality_factors.py). Needs a genuine
  point-in-time cost-of-capital reconstruction, not previously built. Approximations, clearly
  flagged inline:
    - cost of equity: CAPM, reusing load_sec_valuations.py's exact formula (risk_free_rate +
      Blume-adjusted-beta * equity_risk_premium, blume_weight=2/3 toward beta=1.0).
    - risk_free_rate(t): point-in-time DGS10 (economic_data), forward-filled monthly - a real
      historical series, not the production loader's "today only" lookup.
    - equity_risk_premium: production's VIX-scaled dynamic ERP needs a POINT-IN-TIME trailing
      average VIX per month, which is a heavier reconstruction than this pass attempts - uses
      one fixed long-run VIX average (full history) instead of an expanding one. Flagged as a
      real simplification, not silently matching production exactly.
    - beta(t): 24-month rolling beta vs SPY, same construction as
      fama_macbeth_price_factors.py's build_monthly_cross_sections (reused directly).
    - cost of debt: interest_expense / total_debt (same-fiscal-year), after-tax via the same
      effective_tax_rate build_quality_panel() already computes for roic_pct's NOPAT term.
    - capital weights: BOOK values (stockholders_equity vs total_debt) - a real approximation
      vs market-value weights (would need market cap merged in per month); flagged, not hidden.
- net_debt_issuance_yoy: YoY change in NET debt (total_debt - cash_and_equivalents), scaled by
  prior total_assets - distinct from the already-tested GROSS debt_issuance_yoy (EXTENDED_
  CANDIDATE_COLS, t=-1.89 univariate/-1.76 multivariate) which doesn't net out cash. A company
  issuing debt while building an equally large cash pile (e.g. for a pending acquisition) reads
  as high gross issuance but low/zero net issuance - this candidate tests whether the net
  framing is the more informative one.

Usage:
    python -m algo.research.quality_roic_wacc_net_debt_issuance_candidates
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

LIVE_QUALITY_COLS = ["roe", "roa", "roce", "fcf_margin", "debt_to_equity", "interest_coverage", "payout_ratio"]
NEW_CANDIDATES = ["roic_minus_wacc", "net_debt_issuance_yoy"]

DCF_EQUITY_RISK_PREMIUM = 0.05
DCF_MIN_EQUITY_RISK_PREMIUM = 0.03
DCF_MAX_EQUITY_RISK_PREMIUM = 0.08
DCF_BLUME_ADJUSTMENT_WEIGHT = 2.0 / 3.0
DCF_DEFAULT_RISK_FREE_RATE = 0.045


def fetch_econ_series(series_id: str) -> pd.Series:
    with DatabaseContext("read") as cur:
        cur.execute(
            "SELECT date, value FROM economic_data WHERE series_id = %s AND value IS NOT NULL ORDER BY date",
            (series_id,),
        )
        rows = cur.fetchall()
    s = pd.Series({pd.Timestamp(d): float(v) for d, v in rows}).sort_index()
    return s


def build_monthly_wacc_inputs(months: pd.DatetimeIndex) -> pd.DataFrame:
    """Point-in-time monthly risk_free_rate + equity_risk_premium, forward-filled onto `months`."""
    dgs10 = fetch_econ_series("DGS10") / 100.0
    vix = fetch_econ_series("VIXCLS")
    long_run_vix_avg = vix.mean()  # SIMPLIFICATION: fixed full-history average, not expanding/point-in-time

    rfr_monthly = dgs10.reindex(dgs10.index.union(months)).ffill().reindex(months)
    rfr_monthly = rfr_monthly.fillna(DCF_DEFAULT_RISK_FREE_RATE)

    vix_monthly = vix.reindex(vix.index.union(months)).ffill().reindex(months)
    erp_monthly = DCF_EQUITY_RISK_PREMIUM * (vix_monthly / long_run_vix_avg)
    erp_monthly = erp_monthly.clip(DCF_MIN_EQUITY_RISK_PREMIUM, DCF_MAX_EQUITY_RISK_PREMIUM)
    erp_monthly = erp_monthly.fillna(DCF_EQUITY_RISK_PREMIUM)

    return pd.DataFrame({"risk_free_rate": rfr_monthly, "equity_risk_premium": erp_monthly}, index=months)


def build_beta_panel(px: pd.DataFrame, beta_window: int = 24) -> pd.DataFrame:
    """24-month rolling beta vs SPY per symbol per month - mirrors
    fama_macbeth_price_factors.build_monthly_cross_sections' beta construction exactly."""
    ret = px.pct_change(fill_method=None)
    if "SPY" not in ret.columns:
        raise ValueError("SPY not present in price panel - required as the market factor for beta")
    mkt = ret["SPY"]
    months = ret.index
    out = {}
    for i in range(len(months)):
        if i < beta_window:
            continue
        winb = ret.iloc[i - beta_window + 1 : i + 1]
        mkt_win = mkt.iloc[i - beta_window + 1 : i + 1]
        mkt_var = mkt_win.var()
        beta = winb.apply(lambda col, m=mkt_win: col.cov(m)) / mkt_var if mkt_var and mkt_var > 0 else np.nan
        out[months[i]] = beta
    beta_df = pd.DataFrame(out).T
    beta_df = beta_df.drop(columns=["SPY"], errors="ignore")
    return beta_df


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def build_panel(fund: pd.DataFrame) -> pd.DataFrame:
    panel = build_quality_panel(fund)  # gives roe/roa/roce/fcf_margin/debt_to_equity/interest_coverage/payout_ratio

    fund_sorted = fund.sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)
    g = fund_sorted.groupby("symbol", group_keys=False)

    total_debt = fund_sorted["long_term_debt"].fillna(0) + fund_sorted["short_term_debt"].fillna(0)
    net_debt = total_debt - fund_sorted["cash_and_equivalents"].fillna(0)
    prior_net_debt = g.apply(lambda d: net_debt.loc[d.index].shift(1)).reset_index(level=0, drop=True)
    prior_assets = g["total_assets"].shift(1)
    net_debt_issuance_yoy = np.where(prior_assets > 0, (net_debt - prior_net_debt) / prior_assets, np.nan)

    effective_tax_rate = np.where(
        (fund_sorted["pretax_income"] > 0) & fund_sorted["income_tax_expense"].notna(),
        fund_sorted["income_tax_expense"] / fund_sorted["pretax_income"],
        np.nan,
    )
    effective_tax_rate = np.clip(effective_tax_rate, 0.0, 0.5)  # guard against nonsensical extreme rates
    nopat = fund_sorted["operating_income"] * (1 - effective_tax_rate)
    invested_capital = fund_sorted["stockholders_equity"] + total_debt - fund_sorted["cash_and_equivalents"].fillna(0)
    roic_pct = np.where(invested_capital > 0, nopat / invested_capital, np.nan)

    cost_of_debt_pretax = np.where(total_debt > 0, fund_sorted["interest_expense"] / total_debt, np.nan)
    cost_of_debt_pretax = np.clip(cost_of_debt_pretax, 0.0, 0.25)  # guard against garbage ratios
    after_tax_cod = cost_of_debt_pretax * (1 - np.where(np.isnan(effective_tax_rate), 0.21, effective_tax_rate))

    equity_weight = np.where(
        (fund_sorted["stockholders_equity"] + total_debt) > 0,
        fund_sorted["stockholders_equity"].clip(lower=0)
        / (fund_sorted["stockholders_equity"].clip(lower=0) + total_debt),
        np.nan,
    )

    extra = pd.DataFrame(
        {
            "symbol": fund_sorted["symbol"],
            "fiscal_year": fund_sorted["fiscal_year"],
            "net_debt_issuance_yoy": net_debt_issuance_yoy,
            "roic_pct2": roic_pct,
            "after_tax_cod": after_tax_cod,
            "equity_weight": equity_weight,
        }
    )
    merged = panel.merge(extra, on=["symbol", "fiscal_year"], how="left")
    return merged


def _fetch_price_and_beta(start_date: str, end_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    beta_panel = build_beta_panel(px)
    return px, beta_panel


def build_records(start_date: str, end_date: str, min_cross_section: int) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    fund = fetch_annual_quality_fundamentals()
    panel = build_panel(fund)

    px, beta_panel = _fetch_price_and_beta(start_date, end_date)
    months = px.index
    wacc_inputs = build_monthly_wacc_inputs(months)

    all_cols = [*LIVE_QUALITY_COLS, "net_debt_issuance_yoy", "roic_pct2", "after_tax_cod", "equity_weight"]
    monthly = merge_asof_monthly(months, panel, cols=all_cols)

    records = []
    for i in range(len(months) - 1):
        month = months[i]
        qframe = monthly.get(month)
        if qframe is None or qframe.empty:
            continue
        beta_row = beta_panel.loc[month] if month in beta_panel.index else None
        if beta_row is None:
            continue
        rfr = wacc_inputs.loc[month, "risk_free_rate"]
        erp = wacc_inputs.loc[month, "equity_risk_premium"]

        frame = qframe.copy()
        frame["beta"] = beta_row.reindex(frame.index)
        frame = frame.dropna(subset=["beta", "roic_pct2", "after_tax_cod", "equity_weight"])
        if frame.empty:
            continue
        adjusted_beta = DCF_BLUME_ADJUSTMENT_WEIGHT * frame["beta"] + (1 - DCF_BLUME_ADJUSTMENT_WEIGHT) * 1.0
        cost_of_equity = rfr + adjusted_beta * erp
        wacc = frame["equity_weight"] * cost_of_equity + (1 - frame["equity_weight"]) * frame["after_tax_cod"]
        frame["roic_minus_wacc"] = frame["roic_pct2"] - wacc

        fwd_ret = px.iloc[i + 1] / px.iloc[i] - 1.0
        frame = frame.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        for c in [*LIVE_QUALITY_COLS, *NEW_CANDIDATES]:
            if c in frame.columns:
                frame[c] = _zwinsor(frame[c])
        if len(frame.dropna(subset=NEW_CANDIDATES, how="all")) < min_cross_section:
            continue
        records.append((month, frame))
    return records


def run(start_date: str, end_date: str, min_cross_section: int, split_date: str) -> None:
    records = build_records(start_date, end_date, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})\n")

    split_ts = pd.Timestamp(split_date)
    first_half = [r for r in records if pd.Timestamp(r[0]) < split_ts]
    second_half = [r for r in records if pd.Timestamp(r[0]) >= split_ts]

    for label, recs in (
        ("FULL SAMPLE", records),
        (f"FIRST HALF (< {split_date})", first_half),
        (f"SECOND HALF (>= {split_date})", second_half),
    ):
        print(f"--- {label} ({len(recs)} months) UNIVARIATE ---")
        for c in NEW_CANDIDATES:
            usable = [(m, f.dropna(subset=[c])) for m, f in recs]
            usable = [(m, f) for m, f in usable if len(f) >= min_cross_section]
            if not usable:
                print(f"  {c:22s} (no usable months)")
                continue
            result = _fama_macbeth(usable, [c])
            mean, t = result[c]
            avg_n = np.mean([len(f) for _, f in usable])
            print(f"  {c:22s} mean_coef={mean:10.5f}  t_stat={t:7.2f}  n_months={len(usable):4d}  avg_n={avg_n:7.0f}")

        print(f"--- {label} ({len(recs)} months) MULTIVARIATE (controlling for live 7) ---")
        for c in NEW_CANDIDATES:
            cols = [*LIVE_QUALITY_COLS, c]
            usable = [(m, f.dropna(subset=cols)) for m, f in recs]
            usable = [(m, f) for m, f in usable if len(f) >= min_cross_section]
            if not usable:
                print(f"  {c:22s} (no usable months)")
                continue
            result = _fama_macbeth(usable, cols)
            mean, t = result[c]
            print(f"  {c:22s} mean_coef={mean:10.5f}  t_stat={t:7.2f}  n_months={len(usable):4d}")
        print()

    for c in NEW_CANDIDATES:
        coverages = [f[c].notna().mean() for _, f in records]
        print(f"{c} avg point-in-time panel coverage: {np.mean(coverages):.1%}")


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
