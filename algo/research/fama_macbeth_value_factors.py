#!/usr/bin/env python3
"""
Fama-MacBeth cross-sectional regression harness for the Value pillar.

Built 2026-08-25 (goal: re-audit ALL stock_scores inputs without bias toward what already
shipped). Reconstructs point-in-time per-share fundamentals from
annual_income_statement/annual_balance_sheet/annual_cash_flow (same tables and same
calendar-FYE + 90-day-lag point-in-time approximation as
algo/research/fama_macbeth_growth_factors.py - see that module's docstring for the caveat),
merges onto the monthly price panel, and tests P/E, P/B, P/S, FCF yield, dividend yield,
EV/EBITDA, and EV/Revenue jointly. PEG (needs a growth-rate cross-term) and margin-of-safety/
DCF discount (a full valuation model, not a single ratio, and already under separate active
audit per DCF-related fixes landed 2026-08-25) are OUT OF SCOPE here - not tested.

UPDATED 2026-08-25 (same day, later pass - goal: check whether Value's OWN internal weighting
combines its inputs efficiently, following up on
[[composite_weights_reweighted_size_factor_reconfirmed_20260825]]'s side-finding that
value_proxy at live weights scored notably weaker than a standalone Size test). EV/EBITDA and
EV/Revenue REMOVED from VALUE_FACTOR_COLS - already confirmed as PE/PS duplicates and removed
from the live formula the same day (r=1.00/0.93, see load_stock_scores.py's Value docstring),
so re-testing them here would just restate an already-closed finding. Size (log10 market cap,
same point-in-time price*shares_diluted reconstruction as
algo/research/fama_macbeth_composite_weights.py, same sanity bound against the known
shares_diluted scale-error outliers) ADDED, since it's now a live Value input (20% weight) that
this script predates. VALUE_FACTOR_COLS now matches the CURRENT live Value formula's testable
inputs exactly: PE/PB/PS/FCF-yield/dividend-yield/Size (PEG/margin-of-safety still out of scope
per the reasons above).

Ratio convention: every ratio computed from PER-SHARE fundamentals (book value/share, sales/
share, FCF/share, dividend/share, EBITDA/share, net-debt/share) merged with price at scoring
time, so no separate share-count series needs re-joining - e.g. P/B = price / book_value_per_
share, EV/EBITDA = (price + net_debt_per_share) / ebitda_per_share. EBITDA is approximated as
operating_income + depreciation_expense + amortization_expense (this repo's annual_income_
statement schema has no direct EBITDA field). Ratios only computed when both price and the
per-share denominator are positive/defined - a P/E off negative earnings isn't a meaningful
"cheap vs expensive" signal, so those are left NaN rather than guessed, matching
fama_macbeth_growth_factors.py's growth-rate convention.

Usage:
    python -m algo.research.fama_macbeth_value_factors [options]
    (same --start-date/--end-date/--min-cross-section/--horizon-months args as the growth harness)
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import REPORTING_LAG_DAYS, merge_asof_monthly
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

VALUE_FACTOR_COLS = ["pe", "pb", "ps", "fcf_yield", "dividend_yield", "size"]


def fetch_annual_value_fundamentals() -> pd.DataFrame:
    sql = """
        SELECT i.symbol, i.fiscal_year,
               COALESCE(i.diluted_eps, i.eps) AS eps,
               i.revenue, i.operating_income,
               COALESCE(i.depreciation_expense, 0) AS depreciation_expense,
               COALESCE(i.amortization_expense, 0) AS amortization_expense,
               i.shares_outstanding_diluted,
               b.stockholders_equity, b.long_term_debt, b.short_term_debt, b.cash_and_equivalents,
               c.free_cash_flow, c.dividends_paid
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
        "depreciation_expense",
        "amortization_expense",
        "shares_diluted",
        "stockholders_equity",
        "long_term_debt",
        "short_term_debt",
        "cash_and_equivalents",
        "free_cash_flow",
        "dividends_paid",
    ]
    df = pd.DataFrame(rows, columns=cols)
    for c in cols:
        if c not in ("symbol", "fiscal_year"):
            df[c] = df[c].astype(float)
    return df


def build_value_panel(fund: pd.DataFrame) -> pd.DataFrame:
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
    out["shares_diluted"] = shares

    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def compute_ratios(gframe: pd.DataFrame, price: pd.Series) -> pd.DataFrame:
    df = gframe.join(price.rename("price"), how="inner")
    df = df[df["price"] > 0]

    ratios = pd.DataFrame(index=df.index)
    ratios["pe"] = np.where(df["eps"] > 0, df["price"] / df["eps"], np.nan)
    ratios["pb"] = np.where(df["book_value_per_share"] > 0, df["price"] / df["book_value_per_share"], np.nan)
    ratios["ps"] = np.where(df["sales_per_share"] > 0, df["price"] / df["sales_per_share"], np.nan)
    ratios["fcf_yield"] = np.where(df["fcf_per_share"].notna(), df["fcf_per_share"] / df["price"], np.nan)
    ratios["dividend_yield"] = np.where(
        df["dividend_per_share"].notna(), df["dividend_per_share"] / df["price"], np.nan
    )
    ev_per_share = df["price"] + df["net_debt_per_share"]
    ratios["ev_ebitda"] = np.where(df["ebitda_per_share"] > 0, ev_per_share / df["ebitda_per_share"], np.nan)
    ratios["ev_revenue"] = np.where(df["sales_per_share"] > 0, ev_per_share / df["sales_per_share"], np.nan)

    # Size: log10(market_cap), sanity-bounded to a real-world plausible range ($1M-$10T) before
    # taking the log - shares_diluted has known scale-error outliers (observed up to 3.5e15,
    # see SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO / composite_weights_reweighted_size_factor_
    # reconfirmed_20260825 memory), so a handful of corrupted rows can't distort a whole month's
    # z-score via the winsorization quantile boundaries below. Not negated here (unlike the
    # composite script's value_proxy, which flips sign so "higher = better" for every
    # component) - this script reports raw ratios and lets the regression coefficient's own
    # sign show direction, same convention as pe/pb/ps/ev_ebitda/ev_revenue above.
    market_cap = df["price"] * df["shares_diluted"]
    ratios["size"] = np.where((market_cap >= 1e6) & (market_cap <= 1e13), np.log10(market_cap), np.nan)
    return ratios


def run(start_date: str, end_date: str, min_cross_section: int, horizon_months: int = 1) -> None:
    logger.info("Fetching annual value fundamentals (point-in-time reconstruction)")
    fund = fetch_annual_value_fundamentals()
    logger.info(f"{len(fund)} symbol-fiscal-year rows")
    value_panel = build_value_panel(fund)

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    fundamentals_cols = [
        "eps",
        "book_value_per_share",
        "sales_per_share",
        "fcf_per_share",
        "dividend_per_share",
        "ebitda_per_share",
        "net_debt_per_share",
        "shares_diluted",
    ]
    monthly_fund = merge_asof_monthly(months, value_panel, cols=fundamentals_cols)

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i in range(len(months) - horizon_months):
        month = months[i]
        gframe = monthly_fund.get(month)
        if gframe is None or gframe.empty:
            continue
        ratios = compute_ratios(gframe, px.iloc[i])
        fwd_ret = px.iloc[i + horizon_months] / px.iloc[i] - 1.0
        frame = ratios.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        # Only require the columns this run actually tests (VALUE_FACTOR_COLS) plus fwd_ret -
        # ratios also still carries ev_ebitda/ev_revenue (kept computed for anyone re-running
        # the original duplicate-detection comparison) which shouldn't force rows out just for
        # being NaN in a column nothing here regresses on.
        frame = frame.dropna(subset=[*VALUE_FACTOR_COLS, "fwd_ret"])
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        for col in VALUE_FACTOR_COLS:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std > 0 else 0.0
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("=== Multivariate Fama-MacBeth (all value ratios jointly) ===")
    print(f"{'factor':16s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, VALUE_FACTOR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:16s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth (each ratio alone) ===")
    print(f"{'factor':16s} {'mean_coef':>10s} {'t_stat':>8s}")
    for c in VALUE_FACTOR_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:16s} {mean:10.5f} {t:8.2f}")


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
