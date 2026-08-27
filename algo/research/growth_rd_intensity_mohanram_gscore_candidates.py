#!/usr/bin/env python3
"""
Fama-MacBeth validation of 2 Growth candidates unblocked by migration 1239's R&D expense
backfill (2026-08-27): R&D Intensity and Mohanram G-Score (Mohanram 2005, JAR, "Separating
Winners from Losers among Low Book-to-Market Stocks"). Both were marked "permanently blocked,
no R&D data source" in growth_missing_metrics_swept_20260827 - that was wrong, R&D was just
never extracted from the SEC XBRL data this pipeline already fetches; now it's live
(annual_income_statement.research_development_expense, 27.9% of rows / 2,411 symbols populated
universe-wide, naturally sparse since most sectors don't report R&D).

Mirrors algo/research/fama_macbeth_growth_factors.py's conventions exactly: point-in-time
annual-fundamentals reconstruction, REPORTING_LAG_DAYS=90 as-of join onto month-end prices,
1%/99% winsorization + z-scoring per cross-section, full-sample + half-split Fama-MacBeth.

Mohanram G-Score construction (industry-relative, per the original paper - median splits within
fiscal_year x sector, not universe-wide):
  G1: ROA > sector-year median
  G2: Cash-flow ROA (CFO/Assets) > sector-year median
  G3: CFO > Net Income (earnings quality; direct boolean per the original paper, not
      industry-relative like G1/G2)
  G4: trailing-3yr ROA variance < sector-year median variance (more stable = better)
  G5: trailing-3yr sales-growth variance < sector-year median variance
  G6: R&D intensity (R&D/Revenue) > sector-year median
  G7: Capex intensity (Capex/Revenue) > sector-year median

SIMPLIFICATION, documented not hidden: original Mohanram G-Score is 8 signals and includes an
advertising-intensity-vs-industry-median signal (G8). No advertising expense field exists
anywhere in this pipeline (confirmed via information_schema check before writing this) - G8 is
omitted, G-score is summed over 7 signals (0-7) instead of 8 (0-8), same "don't fabricate a
missing input" discipline used throughout this project.
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import (
    GROWTH_FACTOR_COLS,
    REPORTING_LAG_DAYS,
    build_growth_panel,
    fetch_annual_fundamentals,
    merge_asof_monthly,
)
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

CANDIDATE_COLS = ["rd_intensity", "mohanram_g_score"]
LIVE_CONTROL_COLS = [*GROWTH_FACTOR_COLS, "sustainable_growth_rate"]


def fetch_rd_mohanram_fundamentals() -> pd.DataFrame:
    sql = """
        SELECT i.symbol, i.fiscal_year, i.revenue, i.net_income,
               i.research_development_expense,
               c.capex, c.operating_cash_flow,
               b.total_assets,
               cp.sector
        FROM annual_income_statement i
        LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
        LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
        LEFT JOIN company_profile cp ON cp.symbol = i.symbol
        WHERE i.fiscal_year BETWEEN 2000 AND 2026
          AND COALESCE(i.data_unavailable, false) = false
        ORDER BY i.symbol, i.fiscal_year
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    df = pd.DataFrame(
        rows,
        columns=[
            "symbol",
            "fiscal_year",
            "revenue",
            "net_income",
            "rd_expense",
            "capex",
            "ocf",
            "total_assets",
            "sector",
        ],
    )
    for c in ["revenue", "net_income", "rd_expense", "capex", "ocf", "total_assets"]:
        df[c] = df[c].astype(float)
    df["sector"] = df["sector"].fillna("Unknown")
    return df


def build_rd_and_mohanram_panel(fund: pd.DataFrame) -> pd.DataFrame:
    fund = fund.sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)
    g = fund.groupby("symbol", group_keys=False)

    out = fund[["symbol", "fiscal_year", "sector"]].copy()

    # R&D intensity - sparse by construction, only meaningful where R&D is actually reported.
    out["rd_intensity"] = np.where(fund["revenue"] > 0, fund["rd_expense"] / fund["revenue"], np.nan)
    capex_intensity = np.where(fund["revenue"] > 0, fund["capex"].abs() / fund["revenue"], np.nan)
    roa = np.where(fund["total_assets"] > 0, fund["net_income"] / fund["total_assets"], np.nan)
    cf_roa = np.where(fund["total_assets"] > 0, fund["ocf"] / fund["total_assets"], np.nan)

    sales_growth = fund["revenue"] / g["revenue"].shift(1) - 1.0
    sales_growth = sales_growth.where((fund["revenue"] > 0) & (g["revenue"].shift(1) > 0))

    tmp = pd.DataFrame(
        {
            "symbol": fund["symbol"],
            "fiscal_year": fund["fiscal_year"],
            "sector": fund["sector"],
            "roa": roa,
            "cf_roa": cf_roa,
            "ocf_gt_ni": (fund["ocf"] > fund["net_income"])
            .astype(float)
            .where(fund["ocf"].notna() & fund["net_income"].notna()),
            "rd_intensity": out["rd_intensity"],
            "capex_intensity": capex_intensity,
            "sales_growth": sales_growth,
        }
    )
    # Trailing-3yr variance of ROA / sales growth per symbol (min 3 obs required).
    tmp = tmp.set_index(["symbol", "fiscal_year"])
    roa_var = fund.assign(roa=roa).groupby("symbol")["roa"].rolling(3, min_periods=3).var()
    roa_var.index = roa_var.index.droplevel(0)
    sg_var = (
        fund.assign(sales_growth=sales_growth.values).groupby("symbol")["sales_growth"].rolling(3, min_periods=3).var()
    )
    sg_var.index = sg_var.index.droplevel(0)
    tmp["roa_var_3y"] = roa_var
    tmp["sg_var_3y"] = sg_var
    tmp = tmp.reset_index()

    # Sector-year medians for every industry-relative comparison.
    def sector_median(col: str) -> pd.Series:
        return tmp.groupby(["sector", "fiscal_year"])[col].transform("median")

    # FIXED (same NaN-comparison-returns-False-not-NaN bug class this repo has hit before, e.g.
    # quality_asset_turnover_piotroski_candidates.py's Piotroski F-Score) - `NaN > median`
    # silently evaluates to False, not NaN, in pandas/numpy. Explicit .where(notna) re-NaN pass
    # per signal so a missing input is correctly "unknown," not silently "criterion failed."
    def _gt_signal(val: pd.Series, med: pd.Series) -> pd.Series:
        return (val > med).astype(float).where(val.notna() & med.notna())

    def _lt_signal(val: pd.Series, med: pd.Series) -> pd.Series:
        return (val < med).astype(float).where(val.notna() & med.notna())

    g1 = _gt_signal(tmp["roa"], sector_median("roa"))
    g2 = _gt_signal(tmp["cf_roa"], sector_median("cf_roa"))
    g3 = tmp["ocf_gt_ni"]  # direct boolean per Mohanram's own methodology, not industry-relative
    g4 = _lt_signal(tmp["roa_var_3y"], sector_median("roa_var_3y"))
    g5 = _lt_signal(tmp["sg_var_3y"], sector_median("sg_var_3y"))
    g6 = _gt_signal(tmp["rd_intensity"], sector_median("rd_intensity"))
    g7 = _gt_signal(tmp["capex_intensity"], sector_median("capex_intensity"))

    signals = pd.concat([g1, g2, g3, g4, g5, g6, g7], axis=1)
    signals.columns = ["g1", "g2", "g3", "g4", "g5", "g6", "g7"]
    # Require at least 5 of 7 signals computable (same "no thin-sample extrapolation"
    # discipline as this repo's Piotroski F-Score build) - else NaN, not a fabricated score.
    n_avail = signals.notna().sum(axis=1)
    g_score = signals.sum(axis=1, skipna=True)
    out["mohanram_g_score"] = np.where(n_avail >= 5, g_score * (7.0 / n_avail.replace(0, np.nan)), np.nan)

    out["known_date"] = pd.to_datetime(out["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Fetching R&D/Mohanram fundamentals")
    rd_fund = fetch_rd_mohanram_fundamentals()
    rd_panel = build_rd_and_mohanram_panel(rd_fund)

    logger.info("Fetching live-11 growth control panel")
    growth_fund = fetch_annual_fundamentals()
    growth_panel = build_growth_panel(growth_fund)

    # SGR (12th live control, matches loaders/load_stock_scores.py's current _score_growth).
    with DatabaseContext("read") as cur:
        cur.execute(
            """
            SELECT i.symbol, i.fiscal_year, i.net_income, b.stockholders_equity, c.dividends_paid
            FROM annual_income_statement i
            LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
            LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
            WHERE i.fiscal_year BETWEEN 2000 AND 2026 AND COALESCE(i.data_unavailable, false) = false
            """
        )
        sgr_rows = cur.fetchall()
    sgr_fund = pd.DataFrame(
        sgr_rows, columns=["symbol", "fiscal_year", "net_income", "stockholders_equity", "dividends_paid"]
    )
    for c in ["net_income", "stockholders_equity", "dividends_paid"]:
        sgr_fund[c] = sgr_fund[c].astype(float)
    roe = np.where(
        sgr_fund["stockholders_equity"] > 0, sgr_fund["net_income"] / sgr_fund["stockholders_equity"], np.nan
    )
    retention = np.where(
        sgr_fund["net_income"] > 0, 1.0 - sgr_fund["dividends_paid"].abs() / sgr_fund["net_income"], np.nan
    )
    sgr_panel = sgr_fund[["symbol", "fiscal_year"]].copy()
    sgr_panel["sustainable_growth_rate"] = roe * retention
    sgr_panel["known_date"] = pd.to_datetime(sgr_panel["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    sgr_panel = sgr_panel.dropna(subset=["known_date"])

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly_rd = merge_asof_monthly(months, rd_panel, cols=CANDIDATE_COLS)
    monthly_growth = merge_asof_monthly(months, growth_panel, cols=GROWTH_FACTOR_COLS)
    monthly_sgr = merge_asof_monthly(months, sgr_panel, cols=["sustainable_growth_rate"])

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    coverage_counts = {"rd_intensity": 0, "mohanram_g_score": 0, "total": 0}
    for i in range(len(months) - 1):
        month = months[i]
        rdf = monthly_rd.get(month)
        gf = monthly_growth.get(month)
        sf = monthly_sgr.get(month)
        if rdf is None or gf is None or sf is None or rdf.empty or gf.empty:
            continue
        fwd_ret = px.iloc[i + 1] / px.iloc[i] - 1.0
        frame = rdf.join(gf, how="inner").join(sf, how="left").join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        frame = frame.dropna(subset=[*GROWTH_FACTOR_COLS, "fwd_ret"])
        if len(frame) < min_cross_section:
            continue
        coverage_counts["total"] += len(frame)
        coverage_counts["rd_intensity"] += frame["rd_intensity"].notna().sum()
        coverage_counts["mohanram_g_score"] += frame["mohanram_g_score"].notna().sum()
        for col in [*CANDIDATE_COLS, *GROWTH_FACTOR_COLS, "sustainable_growth_rate"]:
            if frame[col].notna().sum() < 10:
                continue
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std and std > 0 else 0.0
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(
        f"Coverage: rd_intensity {100 * coverage_counts['rd_intensity'] / coverage_counts['total']:.1f}%, "
        f"mohanram_g_score {100 * coverage_counts['mohanram_g_score'] / coverage_counts['total']:.1f}% "
        f"of {coverage_counts['total']} symbol-months\n"
    )

    split_idx = len(records) // 2
    halves = {
        "FULL": records,
        "FIRST HALF": records[:split_idx],
        "SECOND HALF": records[split_idx:],
    }

    control_cols = LIVE_CONTROL_COLS
    for label, subset in halves.items():
        print(f"=== {label} ({subset[0][0]} to {subset[-1][0]}, n={len(subset)}) ===")
        for cand in CANDIDATE_COLS:
            # _fama_macbeth assumes a fully clean (no-NaN) frame for whichever cols it's given -
            # build a candidate-specific clean subset per regression rather than reusing the
            # shared `records` (which deliberately keeps rd_intensity/mohanram_g_score sparse -
            # requiring a `.dropna()` across every candidate up front would have wrongly dropped
            # every month for the sparser candidate).
            uni_subset = [
                (m, f.dropna(subset=[cand, "fwd_ret"])) for m, f in subset if f[cand].notna().sum() >= min_cross_section
            ]
            uni_subset = [(m, f) for m, f in uni_subset if len(f) >= min_cross_section]
            multi_subset = [(m, f.dropna(subset=[cand, *control_cols, "fwd_ret"])) for m, f in subset]
            multi_subset = [(m, f) for m, f in multi_subset if len(f) >= min_cross_section]
            if not uni_subset or not multi_subset:
                print(f"  {cand:20s} insufficient coverage for a clean regression in this half")
                continue
            uni = _fama_macbeth(uni_subset, [cand])
            _mean_u, t_u = uni[cand]
            multi = _fama_macbeth(multi_subset, [cand, *control_cols])
            _mean_m, t_m = multi[cand]
            print(
                f"  {cand:20s} univariate t={t_u:6.2f} (n_months={len(uni_subset)})   "
                f"multivariate(ctrl live-12) t={t_m:6.2f} (n_months={len(multi_subset)})"
            )
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
