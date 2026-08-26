#!/usr/bin/env python3
"""
Fama-MacBeth cross-sectional regression harness for the Quality pillar's base score.

Built 2026-08-25 (goal: re-audit ALL stock_scores inputs without bias toward what already
shipped). Tests the actual upstream quality_score formula (load_value_quality_growth_metrics.py,
~line 3313-3330: simple equal-weighted average of roe/roa/operating_margin/net_margin/
debt_to_assets/interest_coverage - see the corrected docstring on StockScoresLoader._score_quality
in loaders/load_stock_scores.py for why the previously-documented "Margins 30% + Profitability
25% + Leverage 25% + Growth 20%" weighting was stale/wrong) using a point-in-time panel
reconstructed the same way as fama_macbeth_growth_factors.py/fama_macbeth_value_factors.py -
same calendar-FYE + 90-day-lag caveat applies.

Ratio definitions (matching the upstream loader's own conventions):
- roe = net_income / stockholders_equity
- roa = net_income / total_assets
- operating_margin = operating_income / revenue
- net_margin = net_income / revenue
- debt_to_assets = (long_term_debt + short_term_debt) / total_assets
- interest_coverage = operating_income / interest_expense (EBIT proxy over interest expense)

Usage:
    python -m algo.research.fama_macbeth_quality_factors [options]
    (same --start-date/--end-date/--min-cross-section/--horizon-months args as the other harnesses)
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

QUALITY_FACTOR_COLS = ["roe", "roa", "operating_margin", "net_margin", "debt_to_assets", "interest_coverage"]

# EXTENDED 2026-08-26 (goal: literature-audit re-check of Quality's candidate input list before
# finalizing weights - see algo/research/fama_macbeth_quality_factors.py's original module
# docstring for the base 6-input test). These 6 candidates were proposed from academic literature
# (Novy-Marx 2013 gross profitability, FF 2015 RMW-style operating profitability, Sloan 1996
# accruals, Bradshaw/Richardson/Sloan 2006 net external financing, QMJ 2013 margin-volatility
# safety leg, Fama/French 2001 + La Porta et al payout policy) but never checked against this
# repo's own point-in-time panel. Tested here as a sanity/direction check only - NOT to derive
# exact final weights from t-stat magnitudes, given the same point-in-time caveats (flat
# calendar-FYE assumption, no true filing-date data, limited independent years) that already
# caused a Growth-pillar backtest-driven reweight to be reverted on user distrust grounds
# (see MEMORY.md growth_quality_inputs_restored_user_distrust_20260826).
EXTENDED_CANDIDATE_COLS = [
    "gross_profitability",
    "operating_profitability",
    "accruals_ratio",
    "share_issuance_yoy",
    "debt_issuance_yoy",
    "margin_volatility_3y",
    "payout_ratio",
]

# altman_z_score gets ITS OWN record-building pass, separate from EXTENDED_CANDIDATE_COLS above -
# same reasoning as that list's own separation from QUALITY_FACTOR_COLS (see _build_records'
# frame.dropna() - a row-wise dropna across every column in one `cols` list). retained_earnings
# (migration 1234, 2026-08-26) started at 0% DB coverage and is being backfilled; bundling
# altman_z_score into EXTENDED_CANDIDATE_COLS while its coverage was 0% wiped out EVERY row via
# that shared dropna (an all-NaN column makes dropna() drop 100% of rows), returning "no usable
# cross-sectional months" for the other 7 already-validated candidates too - not because
# they lost signal, but because one 0%-coverage column poisoned the whole joint dropna. Live-
# caught 2026-08-26 (goal: quality-input completeness pass).
ALTMAN_CANDIDATE_COLS = ["altman_z_score"]

# roic_pct: also isolated (same dropna-poisoning reasoning as ALTMAN_CANDIDATE_COLS above) -
# pretax_income/income_tax_expense/cash_and_equivalents coverage is unknown/unverified up front,
# so don't risk it poisoning EXTENDED_CANDIDATE_COLS' already-validated cross-section.
ROIC_CANDIDATE_COLS = ["roic_pct"]

# NEW 2026-08-26 (goal: user-directed exhaustive-input review, quality-completeness-pass-2).
# Batched into one isolated pass (own dropna scope, separate from everything above) - their
# underlying fields (current_assets/current_liabilities ~69.5%, free_cash_flow ~89% of
# annual_cash_flow rows) have much higher standalone coverage than retained_earnings ever did,
# so joint-dropna poisoning risk is low, but isolating them from the already-validated base-6/
# extended/altman/roic tests above still costs nothing and follows this module's own precedent.
# - roce: EBIT / Capital Employed (Debt + Equity, NO cash netting) - classic textbook ROCE,
#   proposed as a robustness check against roic_pct's own cash-netting failure mode (production's
#   invested_capital = equity + debt - cash goes negative for well-capitalized/cash-rich
#   companies - live-confirmed ~31% of all roic_pct "missing_sec_data" cases in
#   load_value_quality_growth_metrics.py, e.g. ALNY). If roce tests better AND has better
#   coverage than roic_pct, it's a candidate to REPLACE roic_score in the composite, not stack
#   alongside it - same "one representative per dimension" principle already applied to
#   ROE/Operating-Profitability and ROA/Gross-Profitability sharing denominators.
# - fcf_margin: free_cash_flow / revenue. Distinct from accruals_ratio (NI-OCF)/Assets - accruals
#   only checks earnings-vs-cash, never nets out capex, so a capital-intensive business can pass
#   the accruals test while still burning most of its operating cash on capex. fcf_margin catches
#   that. Deliberately NOT also adding capex/sales as a separate candidate: fcf_margin economically
#   IS ocf_margin - capex/sales (FCF = OCF - Capex), so scoring both would double-count the same
#   capital-intensity information under two names.
# - debt_to_equity: quality_metrics stores this today but it has never been scored OR tested -
#   debt_to_assets (already in the composite, evidence-backed t=2.11-2.18) covers the same
#   leverage dimension from a different denominator. Tested here to check for genuinely
#   independent signal, not assumed redundant.
# - current_ratio: liquidity, not previously tested for Quality at all (this repo's Risk pillar
#   doesn't score it either - see quality_pillar_work_landed... note on the CLEANUP 2026-08-16
#   move of debt/liquidity fields out of Stability/Risk display and into quality_inputs display,
#   without ever wiring them into either composite).
NEW_CANDIDATE_COLS = ["roce", "fcf_margin", "debt_to_equity", "current_ratio"]


def fetch_annual_quality_fundamentals() -> pd.DataFrame:
    sql = """
        SELECT i.symbol, i.fiscal_year,
               i.revenue, i.operating_income, i.net_income, i.interest_expense, i.cost_of_revenue,
               i.shares_outstanding_diluted, i.pretax_income, i.income_tax_expense,
               b.stockholders_equity, b.total_assets, b.long_term_debt, b.short_term_debt,
               b.current_assets, b.current_liabilities, b.total_liabilities, b.retained_earnings,
               b.cash_and_equivalents,
               c.operating_cash_flow, c.dividends_paid, c.free_cash_flow
        FROM annual_income_statement i
        LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
        LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
        WHERE i.fiscal_year BETWEEN 2000 AND 2026
          AND COALESCE(i.data_unavailable, false) = false
        ORDER BY i.symbol, i.fiscal_year
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    cols = [
        "symbol",
        "fiscal_year",
        "revenue",
        "operating_income",
        "net_income",
        "interest_expense",
        "cost_of_revenue",
        "shares_outstanding_diluted",
        "pretax_income",
        "income_tax_expense",
        "stockholders_equity",
        "total_assets",
        "long_term_debt",
        "short_term_debt",
        "current_assets",
        "current_liabilities",
        "total_liabilities",
        "retained_earnings",
        "cash_and_equivalents",
        "operating_cash_flow",
        "dividends_paid",
        "free_cash_flow",
    ]
    df = pd.DataFrame(rows, columns=cols)
    for c in cols:
        if c not in ("symbol", "fiscal_year"):
            df[c] = df[c].astype(float)
    return df


def build_quality_panel(fund: pd.DataFrame) -> pd.DataFrame:
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

    # --- Extended candidates (2026-08-26 literature audit) ---
    # Gross Profitability (Novy-Marx 2013): (Revenue - COGS)/Assets
    out["gross_profitability"] = np.where(
        fund["total_assets"] > 0, (fund["revenue"] - fund["cost_of_revenue"]) / fund["total_assets"], np.nan
    )
    # Operating Profitability (FF 2015 RMW-style): (OperatingIncome - Interest)/BookEquity.
    # No separate SG&A field exists in this pipeline; GAAP operating_income already nets out
    # COGS+SG&A, so (operating_income - interest_expense) is the correct available proxy for
    # FF's (Rev-COGS-SGA-Interest) construction - interest is the one term operating_income
    # doesn't already remove.
    out["operating_profitability"] = np.where(
        fund["stockholders_equity"] > 0,
        (fund["operating_income"] - fund["interest_expense"].fillna(0)) / fund["stockholders_equity"],
        np.nan,
    )
    # Accruals Ratio (Sloan 1996, Hribar-Collins cash-flow-statement shortcut): (NI - OCF)/Assets
    out["accruals_ratio"] = np.where(
        fund["total_assets"] > 0, (fund["net_income"] - fund["operating_cash_flow"]) / fund["total_assets"], np.nan
    )
    # Payout Ratio: dividends_paid is a cash outflow (reported <= 0 in this schema) - flip sign.
    out["payout_ratio"] = np.where(
        fund["net_income"] > 0, -fund["dividends_paid"].fillna(0) / fund["net_income"], np.nan
    )

    # ROIC (2026-08-26): quality_score's roic_score component (10% weight) had never been run
    # through this harness at all, unlike every other component - approximates
    # load_value_quality_growth_metrics.py's real production formula (NOPAT = operating_income
    # * (1 - effective_tax_rate); invested_capital = equity + debt - cash). Not an exact mirror:
    # production's debt term prefers sec_valuations.total_debt with a multi-year long_term_debt
    # fallback; this uses the same-fiscal-year long_term_debt + short_term_debt sum, a simpler
    # but directionally equivalent debt proxy - fine for a sanity/direction check, not for
    # deriving exact weights (same caveat as every other candidate in this module).
    effective_tax_rate = np.where(
        (fund["pretax_income"] > 0) & fund["income_tax_expense"].notna(),
        fund["income_tax_expense"] / fund["pretax_income"],
        np.nan,
    )
    nopat = fund["operating_income"] * (1 - effective_tax_rate)
    invested_capital = (
        fund["stockholders_equity"]
        + fund["long_term_debt"].fillna(0)
        + fund["short_term_debt"].fillna(0)
        - fund["cash_and_equivalents"]
    )
    out["roic_pct"] = np.where(invested_capital > 0, nopat / invested_capital, np.nan)

    # Altman Z''-Score (Altman 1995, the book-equity private-firm/non-manufacturer variant -
    # not the original 1968 Z-Score, which uses Market Value of Equity/Total Liabilities for
    # X4 and adds a Sales/Assets X5 term). Chosen deliberately over the market-cap variant:
    # this repo already has a Value pillar scoring market-cap-derived ratios, and a prior
    # attempt to score raw market cap directly as its own "Size" pillar was implemented then
    # fully reverted the same day on user directive (see MEMORY.md
    # size_pillar_removed_entirely_20260826) - reusing book equity here keeps Quality a
    # pure-fundamentals pillar and doesn't reopen that question. Built to test whether Z''
    # resolves the debt_to_assets sign tension noted in load_value_quality_growth_metrics.py's
    # quality_score construction (MM leverage-beta vs. Campbell/Hilscher/Szilagyi 2008 distress
    # anomaly) - retained_earnings only just became available via migration 1234.
    working_capital = fund["current_assets"] - fund["current_liabilities"]
    x1 = np.where(fund["total_assets"] > 0, working_capital / fund["total_assets"], np.nan)
    x2 = np.where(fund["total_assets"] > 0, fund["retained_earnings"] / fund["total_assets"], np.nan)
    x3 = np.where(fund["total_assets"] > 0, fund["operating_income"] / fund["total_assets"], np.nan)
    x4 = np.where(fund["total_liabilities"] > 0, fund["stockholders_equity"] / fund["total_liabilities"], np.nan)
    out["altman_z_score"] = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4

    # --- NEW_CANDIDATE_COLS (2026-08-26 user-directed exhaustive-input review) ---
    # ROCE: EBIT / Capital Employed, Capital Employed = Debt + Equity (NO cash subtraction -
    # this is the deliberate difference from roic_pct above, see NEW_CANDIDATE_COLS' own
    # comment). operating_income is used as the EBIT proxy, same convention this module
    # already uses for interest_coverage/operating_profitability/altman_z's x3 term.
    capital_employed = fund["stockholders_equity"] + total_debt
    out["roce"] = np.where(capital_employed > 0, fund["operating_income"] / capital_employed, np.nan)
    # FCF Margin: free_cash_flow / revenue - cash-conversion efficiency net of capex, distinct
    # from accruals_ratio (see NEW_CANDIDATE_COLS comment for why).
    out["fcf_margin"] = np.where(fund["revenue"] > 0, fund["free_cash_flow"] / fund["revenue"], np.nan)
    # Debt-to-Equity: same total_debt numerator as debt_to_assets above, equity denominator
    # instead of assets. No |ratio|>1000 style implausibility clamp here (unlike production's
    # loader) - _build_records' own 1st/99th percentile winsorization below handles outliers for
    # this harness's purposes.
    out["debt_to_equity"] = np.where(fund["stockholders_equity"] > 0, total_debt / fund["stockholders_equity"], np.nan)
    # Current Ratio: current_assets / current_liabilities - the same two fields already used for
    # Altman Z's working_capital term above, just as a ratio instead of a difference.
    out["current_ratio"] = np.where(
        fund["current_liabilities"] > 0, fund["current_assets"] / fund["current_liabilities"], np.nan
    )

    fund_sorted = fund.sort_values(["symbol", "fiscal_year"]).copy()
    fund_sorted["total_debt"] = fund_sorted["long_term_debt"].fillna(0) + fund_sorted["short_term_debt"].fillna(0)
    grp = fund_sorted.groupby("symbol")
    prior_shares = grp["shares_outstanding_diluted"].shift(1)
    prior_debt = grp["total_debt"].shift(1)
    prior_assets = grp["total_assets"].shift(1)
    share_issuance = np.where(
        (prior_shares > 0), (fund_sorted["shares_outstanding_diluted"] - prior_shares) / prior_shares, np.nan
    )
    debt_issuance = np.where((prior_assets > 0), (fund_sorted["total_debt"] - prior_debt) / prior_assets, np.nan)
    # Margin volatility (QMJ Safety leg proxy): trailing-3yr stdev of net_margin per symbol.
    net_margin_sorted = np.where(fund_sorted["revenue"] > 0, fund_sorted["net_income"] / fund_sorted["revenue"], np.nan)
    margin_vol = (
        pd.Series(net_margin_sorted, index=fund_sorted.index)
        .groupby(fund_sorted["symbol"])
        .rolling(window=3, min_periods=3)
        .std()
        .reset_index(level=0, drop=True)
    )

    extended = pd.DataFrame(
        {
            "share_issuance_yoy": share_issuance,
            "debt_issuance_yoy": debt_issuance,
            "margin_volatility_3y": margin_vol,
        },
        index=fund_sorted.index,
    ).reindex(out.index)
    out = out.join(extended)

    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def _build_records(
    months: pd.DatetimeIndex,
    px: pd.DataFrame,
    panel: pd.DataFrame,
    cols: list[str],
    horizon_months: int,
    min_cross_section: int,
) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    monthly = merge_asof_monthly(months, panel, cols=cols)
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i in range(len(months) - horizon_months):
        month = months[i]
        qframe = monthly.get(month)
        if qframe is None or qframe.empty:
            continue
        fwd_ret = px.iloc[i + horizon_months] / px.iloc[i] - 1.0
        frame = qframe.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        for col in cols:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std > 0 else 0.0
        records.append((month, frame))
    return records


def run(start_date: str, end_date: str, min_cross_section: int, horizon_months: int = 1) -> None:
    logger.info("Fetching annual quality fundamentals (point-in-time reconstruction)")
    fund = fetch_annual_quality_fundamentals()
    logger.info(f"{len(fund)} symbol-fiscal-year rows")
    quality_panel = build_quality_panel(fund)

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    records = _build_records(months, px, quality_panel, QUALITY_FACTOR_COLS, horizon_months, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("=== Multivariate Fama-MacBeth (all quality-score components jointly) ===")
    print(f"{'factor':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, QUALITY_FACTOR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth (each base component alone) ===")
    print(f"{'factor':18s} {'mean_coef':>10s} {'t_stat':>8s}")
    for c in QUALITY_FACTOR_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:18s} {mean:10.5f} {t:8.2f}")

    # Extended candidates get their own record-building pass (separate dropna scope) so their
    # lower/uneven coverage (cost_of_revenue ~54%, margin_volatility_3y needs 3 consecutive
    # fiscal years, etc.) doesn't shrink or bias the base-6 test above, and vice versa.
    ext_records = _build_records(months, px, quality_panel, EXTENDED_CANDIDATE_COLS, horizon_months, min_cross_section)
    if not ext_records:
        print("\n(no usable cross-sectional months for extended candidates - coverage too sparse)")
    else:
        ext_sizes = [len(f) for _, f in ext_records]
        print(
            f"\n=== Extended candidates: {len(ext_records)} usable months "
            f"({ext_records[0][0]} to {ext_records[-1][0]}), median cross-section {int(np.median(ext_sizes))} ==="
        )
        print("\n=== Univariate Fama-MacBeth (each extended candidate alone) ===")
        print(f"{'factor':22s} {'mean_coef':>10s} {'t_stat':>8s}")
        for c in EXTENDED_CANDIDATE_COLS:
            uni = _fama_macbeth(ext_records, [c])
            mean, t = uni[c]
            print(f"{c:22s} {mean:10.5f} {t:8.2f}")

        print("\n=== Multivariate Fama-MacBeth (extended candidates jointly) ===")
        print(f"{'factor':22s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
        ext_multi = _fama_macbeth(ext_records, EXTENDED_CANDIDATE_COLS)
        for name, (mean, t) in ext_multi.items():
            print(f"{name:22s} {mean:10.5f} {t:8.2f} {len(ext_records):9d}")

    # Altman Z''-Score: its own record-building pass, isolated from EXTENDED_CANDIDATE_COLS -
    # see ALTMAN_CANDIDATE_COLS' own comment for why (retained_earnings coverage is still
    # ramping up from a 2026-08-26 backfill, unlike the other 7 candidates above).
    z_records = _build_records(months, px, quality_panel, ALTMAN_CANDIDATE_COLS, horizon_months, min_cross_section)
    if not z_records:
        print("\n(no usable cross-sectional months for altman_z_score - retained_earnings coverage too sparse)")
    else:
        z_sizes = [len(f) for _, f in z_records]
        print(
            f"\n=== Altman Z''-Score: {len(z_records)} usable months "
            f"({z_records[0][0]} to {z_records[-1][0]}), median cross-section {int(np.median(z_sizes))} ==="
        )
        z_uni = _fama_macbeth(z_records, ALTMAN_CANDIDATE_COLS)
        mean, t = z_uni["altman_z_score"]
        print(f"{'altman_z_score':22s} {mean:10.5f} {t:8.2f}")

    # roic_pct: also isolated - see ROIC_CANDIDATE_COLS' own comment for why.
    roic_records = _build_records(months, px, quality_panel, ROIC_CANDIDATE_COLS, horizon_months, min_cross_section)
    if not roic_records:
        print("\n(no usable cross-sectional months for roic_pct - coverage too sparse)")
        return
    roic_sizes = [len(f) for _, f in roic_records]
    print(
        f"\n=== ROIC: {len(roic_records)} usable months "
        f"({roic_records[0][0]} to {roic_records[-1][0]}), median cross-section {int(np.median(roic_sizes))} ==="
    )
    roic_uni = _fama_macbeth(roic_records, ROIC_CANDIDATE_COLS)
    mean, t = roic_uni["roic_pct"]
    print(f"{'roic_pct':22s} {mean:10.5f} {t:8.2f}")

    # NEW_CANDIDATE_COLS: roce, fcf_margin, debt_to_equity, current_ratio - see that constant's
    # own comment for why each was proposed and why they're batched into one isolated pass.
    new_records = _build_records(months, px, quality_panel, NEW_CANDIDATE_COLS, horizon_months, min_cross_section)
    if not new_records:
        print("\n(no usable cross-sectional months for roce/fcf_margin/debt_to_equity/current_ratio)")
        return
    new_sizes = [len(f) for _, f in new_records]
    print(
        f"\n=== New candidates (roce/fcf_margin/debt_to_equity/current_ratio): {len(new_records)} "
        f"usable months ({new_records[0][0]} to {new_records[-1][0]}), "
        f"median cross-section {int(np.median(new_sizes))} ==="
    )
    print("\n=== Univariate Fama-MacBeth (each new candidate alone) ===")
    print(f"{'factor':18s} {'mean_coef':>10s} {'t_stat':>8s}")
    for c in NEW_CANDIDATE_COLS:
        uni = _fama_macbeth(new_records, [c])
        mean, t = uni[c]
        print(f"{c:18s} {mean:10.5f} {t:8.2f}")

    print("\n=== Multivariate Fama-MacBeth (new candidates jointly) ===")
    print(f"{'factor':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    new_multi = _fama_macbeth(new_records, NEW_CANDIDATE_COLS)
    for name, (mean, t) in new_multi.items():
        print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(new_records):9d}")

    # roce vs roic_pct: also check whether roce actually improves on roic_pct's known coverage
    # gap (see NEW_CANDIDATE_COLS comment - ~31% of roic_pct failures are negative invested
    # capital from cash-netting). Coverage-in-the-panel is a decent proxy for that same
    # cash-netting failure mode reproducing itself here.
    roic_coverage = quality_panel["roic_pct"].notna().mean()
    roce_coverage = quality_panel["roce"].notna().mean()
    print(f"\nroic_pct point-in-time panel coverage: {roic_coverage:.1%}")
    print(f"roce point-in-time panel coverage: {roce_coverage:.1%}")


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
