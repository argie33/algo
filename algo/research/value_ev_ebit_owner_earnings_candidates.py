#!/usr/bin/env python3
"""
Tests 2 genuinely untested Value candidates: EV/EBIT and Owner Earnings Yield.

Built 2026-08-27 (goal: close out the user-supplied Value checklist's remaining gaps after
EV/EBITDA and EV/Revenue were already tested and REMOVED as PE/PS duplicates - see
fama_macbeth_value_factors.py's own docstring, r=1.00/0.93 with PE/PS). EV/EBIT swaps EBITDA
for EBIT (post-D&A, operating_income) - a capital-structure-neutral multiple like EV/EBITDA but
one that doesn't ignore depreciation, arguably a cleaner "quality of earnings" cousin worth
testing on its own despite the EV/EBITDA removal precedent (D&A intensity varies enough across
industries that EV/EBIT and EV/EBITDA aren't identical rankings).

Owner Earnings Yield (Buffett, 1986 Berkshire shareholder letter) = (Net Income + D&A -
Maintenance Capex - Change in Net Working Capital) / Market Cap. This repo's schema has no
maintenance-vs-growth capex split (same gap fcf_yield already lives with), so this script uses
TOTAL capex as the maintenance-capex proxy - the same simplification this repo's existing
free_cash_flow field already makes (FCF = OCF - total capex, not OCF - maintenance capex only),
so Owner Earnings here is directly comparable in spirit to the live fcf_yield input, just with
the net-income-plus-D&A-minus-NWC-change starting point instead of OCF. This makes Owner
Earnings Yield's incremental value over fcf_yield specifically about whether starting from
accrual net income (adjusted back toward cash) captures something OCF's own accrual noise
doesn't - not about a better capex split, which isn't available either way.

Multivariate control uses this script's own established VALUE_FACTOR_COLS (pe/pb/ps/fcf_yield/
dividend_yield/size) from fama_macbeth_value_factors.py, NOT a full reconstruction of live
_score_value's exact 7-input formula (PEG needs a growth cross-term, margin-of-safety is a full
DCF model) - that exact scope carve-out is already established and documented in
fama_macbeth_value_factors.py's own docstring ("OUT OF SCOPE here - not tested"), applied
identically here rather than re-litigated.

Usage:
    python -m algo.research.value_ev_ebit_owner_earnings_candidates [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import REPORTING_LAG_DAYS, merge_asof_monthly
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_value_factors import VALUE_FACTOR_COLS, compute_ratios
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

NEW_CANDIDATE_COLS = ["ev_ebit", "owner_earnings_yield"]


def fetch_annual_fundamentals_extended() -> pd.DataFrame:
    """Same base panel as fama_macbeth_value_factors.fetch_annual_value_fundamentals, extended
    with net_income/capex/current_assets/current_liabilities for the 2 new candidates."""
    sql = """
        SELECT i.symbol, i.fiscal_year,
               COALESCE(i.diluted_eps, i.eps) AS eps,
               i.revenue, i.operating_income, i.net_income,
               COALESCE(i.depreciation_expense, 0) AS depreciation_expense,
               COALESCE(i.amortization_expense, 0) AS amortization_expense,
               i.shares_outstanding_diluted,
               b.stockholders_equity, b.long_term_debt, b.short_term_debt, b.cash_and_equivalents,
               b.current_assets, b.current_liabilities,
               c.free_cash_flow, c.dividends_paid, c.capex
        FROM annual_income_statement i
        LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
        LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
        WHERE i.fiscal_year BETWEEN 2000 AND 2026
          AND COALESCE(i.data_unavailable, false) = false
          AND i.shares_outstanding_diluted > 0
        ORDER BY i.symbol, i.fiscal_year
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    cols = [
        "symbol",
        "fiscal_year",
        "eps",
        "revenue",
        "operating_income",
        "net_income",
        "depreciation_expense",
        "amortization_expense",
        "shares_diluted",
        "stockholders_equity",
        "long_term_debt",
        "short_term_debt",
        "cash_and_equivalents",
        "current_assets",
        "current_liabilities",
        "free_cash_flow",
        "dividends_paid",
        "capex",
    ]
    df = pd.DataFrame(rows, columns=cols)
    for c in cols:
        if c not in ("symbol", "fiscal_year"):
            df[c] = df[c].astype(float)
    return df


def build_extended_panel(fund: pd.DataFrame) -> pd.DataFrame:
    fund = fund.sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)
    shares = fund["shares_diluted"]
    net_debt = (
        fund["long_term_debt"].fillna(0) + fund["short_term_debt"].fillna(0) - fund["cash_and_equivalents"].fillna(0)
    )
    nwc = fund["current_assets"] - fund["current_liabilities"]
    g = fund.groupby("symbol", group_keys=False)
    delta_nwc = nwc - g["current_assets"].shift(1).combine(g["current_liabilities"].shift(1), lambda a, b: a - b)
    # owner earnings = NI + D&A - capex(proxy for maint. capex) - ΔNWC, all per-share
    owner_earnings = (
        fund["net_income"]
        + fund["depreciation_expense"]
        + fund["amortization_expense"]
        - fund["capex"].abs()
        - delta_nwc
    )

    out = fund[["symbol", "fiscal_year"]].copy()
    out["eps"] = fund["eps"]
    out["book_value_per_share"] = fund["stockholders_equity"] / shares
    out["sales_per_share"] = fund["revenue"] / shares
    out["fcf_per_share"] = fund["free_cash_flow"] / shares
    out["dividend_per_share"] = fund["dividends_paid"].abs() / shares
    out["net_debt_per_share"] = net_debt / shares
    out["shares_diluted"] = shares
    out["ebitda_per_share"] = (
        fund["operating_income"] + fund["depreciation_expense"] + fund["amortization_expense"]
    ) / shares
    out["ebit_per_share"] = fund["operating_income"] / shares
    out["owner_earnings_per_share"] = owner_earnings / shares
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def compute_new_ratios(gframe: pd.DataFrame, price: pd.Series) -> pd.DataFrame:
    df = gframe.join(price.rename("price"), how="inner")
    df = df[df["price"] > 0]
    ratios = pd.DataFrame(index=df.index)
    ev_per_share = df["price"] + df["net_debt_per_share"]
    ratios["ev_ebit"] = np.where(df["ebit_per_share"] > 0, ev_per_share / df["ebit_per_share"], np.nan)
    # sign-flipped to "yield" convention (higher = cheaper = expected better), matching
    # fcf_yield/dividend_yield's own orientation rather than ev_ebit's "multiple" orientation
    # above (lower multiple = cheaper, opposite sign convention - intentional, matches how this
    # script family already mixes multiples (pe/pb/ps/ev_ebit, low=cheap) and yields
    # (fcf_yield/dividend_yield/owner_earnings_yield, high=cheap) side by side).
    ratios["owner_earnings_yield"] = np.where(
        df["owner_earnings_per_share"].notna(), df["owner_earnings_per_share"] / df["price"], np.nan
    )
    return ratios


def _half_split(
    records: list[tuple[pd.Timestamp, pd.DataFrame]],
) -> tuple[list[tuple[pd.Timestamp, pd.DataFrame]], list[tuple[pd.Timestamp, pd.DataFrame]]]:
    idx = len(records) // 2
    return records[:idx], records[idx:]


def run(start_date: str, end_date: str, min_cross_section: int, horizon_months: int = 1) -> None:
    logger.info("Fetching extended value fundamentals")
    fund = fetch_annual_fundamentals_extended()
    panel = build_extended_panel(fund)

    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    fundamentals_cols = [
        "eps",
        "book_value_per_share",
        "sales_per_share",
        "fcf_per_share",
        "dividend_per_share",
        "net_debt_per_share",
        "shares_diluted",
        "ebitda_per_share",
        "ebit_per_share",
        "owner_earnings_per_share",
    ]
    monthly_fund = merge_asof_monthly(months, panel, cols=fundamentals_cols)

    all_cols = VALUE_FACTOR_COLS + NEW_CANDIDATE_COLS
    records = []
    for i in range(len(months) - horizon_months):
        month = months[i]
        gframe = monthly_fund.get(month)
        if gframe is None or gframe.empty:
            continue
        old_ratios = compute_ratios(gframe, px.iloc[i])
        new_ratios = compute_new_ratios(gframe, px.iloc[i])
        ratios = old_ratios.join(new_ratios, how="outer")
        fwd_ret = px.iloc[i + horizon_months] / px.iloc[i] - 1.0
        frame = ratios.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame.dropna(subset=["fwd_ret"])
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        for col in all_cols:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std and std > 0 else frame[col] * 0.0
        frame[all_cols] = frame[all_cols].fillna(0.0)
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median([len(f) for _, f in records]))}\n")

    print("=== Univariate (each new candidate alone) ===")
    for c in NEW_CANDIDATE_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:24s} full: t={t:6.2f}")

    print("\n=== Sanity check: live VALUE_FACTOR_COLS univariate, for sign-convention reference ===")
    for c in VALUE_FACTOR_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:24s} full: t={t:6.2f}  mean_coef={mean:8.5f}")

    print("\n=== Multivariate (new candidate + live 6 VALUE_FACTOR_COLS jointly) ===")
    for c in NEW_CANDIDATE_COLS:
        multi = _fama_macbeth(records, [*VALUE_FACTOR_COLS, c])
        mean, t = multi[c]
        print(f"{c:24s} full: t={t:6.2f}  (controlling for {VALUE_FACTOR_COLS})")

    first_half, second_half = _half_split(records)
    print(
        f"\n=== Half-split (multivariate-controlled): "
        f"1st {first_half[0][0]}-{first_half[-1][0]}, 2nd {second_half[0][0]}-{second_half[-1][0]} ==="
    )
    for c in NEW_CANDIDATE_COLS:
        m1 = _fama_macbeth(first_half, [*VALUE_FACTOR_COLS, c])
        m2 = _fama_macbeth(second_half, [*VALUE_FACTOR_COLS, c])
        print(f"{c:24s} 1st half t={m1[c][1]:6.2f}   2nd half t={m2[c][1]:6.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--horizon-months", type=int, default=1)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.horizon_months)


if __name__ == "__main__":
    main()
