#!/usr/bin/env python3
"""Diagnostic (read-only): cross-statement tie-out checks for annual_balance_sheet /
annual_cash_flow.

Goal-session tool (2026-09-06, "should we track more XBRL data" review): the concept-
priority/magnitude-resolution machinery in loaders/helpers/sec_base.py and
load_financial_statements.py picks a value per field independently - nothing in the
pipeline today cross-checks that a symbol/year's picked values are internally
consistent with each other. Every real bug this codebase's SEC/XBRL campaign found by
hand (BBVA/HSBC revenue magnitude collision, ORLY revenue clobbered by an interest-
income fact, Berkshire's split-entity debt, etc.) was a case where SOME extracted value
was wrong in a way that would have failed a basic accounting identity. This script
surfaces symbols/years that fail those identities, for follow-up investigation - it does
NOT write anything back to the DB, does NOT mark any row data_unavailable, and does NOT
change any score. Wiring a tie-out failure into the live loader pipeline (and into
lambda/api/routes/scores_handlers/coverage_category_rules.py's category map) is a
separate, deliberate follow-up decision - not made here, since it would change which
rows scoring treats as usable.

Two checks:

1. Balance sheet identity: total_assets == total_liabilities + stockholders_equity.
   NOTE: load_financial_statements.py derives total_liabilities = total_assets -
   stockholders_equity whenever a filer never tags "Liabilities" directly (see that
   file's 2026-08-18 REX American Resources fix) - those rows tie out by construction
   and are silently uninformative here, not falsely "passing" a real check. Only rows
   where a real, filer-tagged total_liabilities disagrees with the other two are
   flagged.

2. Cash flow reconciliation: prior-year cash_and_equivalents + operating_cash_flow +
   investing_cash_flow + financing_cash_flow ~= current-year cash_and_equivalents.
   No effect-of-exchange-rate-changes concept is tracked anywhere in this schema, so a
   multinational filer's real FX-driven cash movement always shows up as residual noise
   here - tolerance is deliberately generous (see _CASHFLOW_TOLERANCE_PCT) to avoid
   flagging that noise as a tie-out failure.

Usage: python scripts/audit_statement_tie_outs.py [--min-relative-error 0.01] [--limit 50]
"""

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.db.context import DatabaseContext

_BALANCE_SHEET_TOLERANCE_PCT = 0.01  # 1% of total_assets
_CASHFLOW_TOLERANCE_PCT = 0.10  # 10% of |ending cash| - generous, no FX-effect concept tracked
_CASHFLOW_TOLERANCE_FLOOR = 1_000_000.0  # never flag a sub-$1M residual (rounding/immateriality)


def _table_has_columns(cur: Any, table: str, columns: set[str]) -> bool:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
        (table,),
    )
    present = {r[0] for r in cur.fetchall()}
    return columns.issubset(present)


def audit_balance_sheet_identity(cur: Any, min_relative_error: float, limit: int) -> list[tuple[Any, ...]]:
    if not _table_has_columns(
        cur,
        "annual_balance_sheet",
        {"symbol", "fiscal_year", "total_assets", "total_liabilities", "stockholders_equity"},
    ):
        print("  [SKIP] annual_balance_sheet missing required columns")
        return []
    cur.execute(
        """
        SELECT b.symbol, b.fiscal_year, b.total_assets, b.total_liabilities, b.stockholders_equity
        FROM annual_balance_sheet b
        JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
        WHERE b.data_unavailable = FALSE
          AND b.total_assets IS NOT NULL
          AND b.total_liabilities IS NOT NULL
          AND b.stockholders_equity IS NOT NULL
          AND b.total_assets != 0
        """
    )
    flagged = []
    for symbol, fiscal_year, assets, liabilities, equity in cur.fetchall():
        assets_f, liabilities_f, equity_f = float(assets), float(liabilities), float(equity)
        # Rows where total_liabilities was derived as assets-equity tie out exactly (0
        # residual) by construction - harmless, just uninformative, not a false pass of a
        # real check that was never actually performed for them.
        residual = assets_f - (liabilities_f + equity_f)
        relative_error = abs(residual) / abs(assets_f)
        if relative_error > min_relative_error:
            flagged.append((symbol, fiscal_year, assets_f, liabilities_f, equity_f, residual, relative_error))
    flagged.sort(key=lambda r: r[-1], reverse=True)
    return flagged[:limit]


def audit_cashflow_reconciliation(cur: Any, limit: int) -> list[tuple[Any, ...]]:
    if not _table_has_columns(
        cur,
        "annual_cash_flow",
        {"symbol", "fiscal_year", "operating_cash_flow", "investing_cash_flow", "financing_cash_flow"},
    ) or not _table_has_columns(cur, "annual_balance_sheet", {"symbol", "fiscal_year", "cash_and_equivalents"}):
        print("  [SKIP] annual_cash_flow/annual_balance_sheet missing required columns")
        return []
    cur.execute(
        """
        WITH cf AS (
            SELECT symbol, fiscal_year, operating_cash_flow, investing_cash_flow, financing_cash_flow
            FROM annual_cash_flow
            WHERE data_unavailable = FALSE
              AND operating_cash_flow IS NOT NULL
              AND investing_cash_flow IS NOT NULL
              AND financing_cash_flow IS NOT NULL
        ),
        cash AS (
            SELECT symbol, fiscal_year, cash_and_equivalents
            FROM annual_balance_sheet
            WHERE data_unavailable = FALSE AND cash_and_equivalents IS NOT NULL
        )
        SELECT
            cf.symbol, cf.fiscal_year,
            cf.operating_cash_flow, cf.investing_cash_flow, cf.financing_cash_flow,
            prior.cash_and_equivalents AS prior_cash,
            curr.cash_and_equivalents AS curr_cash
        FROM cf
        JOIN stock_symbols s ON s.symbol = cf.symbol AND s.active = true
        JOIN cash curr ON curr.symbol = cf.symbol AND curr.fiscal_year = cf.fiscal_year
        JOIN cash prior ON prior.symbol = cf.symbol AND prior.fiscal_year = cf.fiscal_year - 1
        """
    )
    flagged = []
    for symbol, fiscal_year, ocf, icf, fcf, prior_cash, curr_cash in cur.fetchall():
        ocf_f, icf_f, fcf_f = float(ocf), float(icf), float(fcf)
        prior_f, curr_f = float(prior_cash), float(curr_cash)
        implied_curr = prior_f + ocf_f + icf_f + fcf_f
        residual = implied_curr - curr_f
        tolerance = max(_CASHFLOW_TOLERANCE_FLOOR, abs(curr_f) * _CASHFLOW_TOLERANCE_PCT)
        if abs(residual) > tolerance:
            flagged.append((symbol, fiscal_year, ocf_f, icf_f, fcf_f, prior_f, curr_f, residual))
    flagged.sort(key=lambda r: abs(r[-1]), reverse=True)
    return flagged[:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-relative-error", type=float, default=_BALANCE_SHEET_TOLERANCE_PCT)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    print("=== Balance sheet identity check (total_assets == total_liabilities + stockholders_equity) ===")
    print(
        f"(flagging relative error > {args.min_relative_error:.1%}; derived-liability rows tie out trivially, excluded from consideration)\n"
    )
    with DatabaseContext("read") as cur:
        bs_flagged = audit_balance_sheet_identity(cur, args.min_relative_error, args.limit)
    if not bs_flagged:
        print("  No violations found.\n")
    else:
        for symbol, fiscal_year, assets, liabilities, equity, residual, relative_error in bs_flagged:
            print(
                f"  {symbol:<8} FY{fiscal_year}  assets={assets:,.0f}  liabilities={liabilities:,.0f}  "
                f"equity={equity:,.0f}  residual={residual:,.0f}  ({relative_error:.1%})"
            )
        print()

    print("=== Cash flow reconciliation check (prior cash + OCF + ICF + FCF ~= current cash) ===")
    print(
        f"(flagging residual > max(${_CASHFLOW_TOLERANCE_FLOOR:,.0f}, {_CASHFLOW_TOLERANCE_PCT:.0%} of ending cash) - no FX-effect concept tracked, expect some multinational noise)\n"
    )
    with DatabaseContext("read") as cur:
        cf_flagged = audit_cashflow_reconciliation(cur, args.limit)
    if not cf_flagged:
        print("  No violations found.\n")
    else:
        for symbol, fiscal_year, ocf, icf, fcf, prior_cash, curr_cash, residual in cf_flagged:
            print(
                f"  {symbol:<8} FY{fiscal_year}  OCF={ocf:,.0f}  ICF={icf:,.0f}  FCF={fcf:,.0f}  "
                f"prior_cash={prior_cash:,.0f}  curr_cash={curr_cash:,.0f}  residual={residual:,.0f}"
            )
        print()


if __name__ == "__main__":
    main()
