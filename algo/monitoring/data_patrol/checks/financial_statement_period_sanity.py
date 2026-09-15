#!/usr/bin/env python3
"""Detects financial-statement rows whose fiscal_year/fiscal_quarter (or, for
quarterly_income_statement, period_end) implies a period that has not happened yet.

GAP FOUND 2026-09-15 (/goal "desloppify scores" session, live-caught via SMMT, CIK
0001599298): the cross-concept fiscal-year-end conflict fix in
utils/external/sec_statements_aggregate.py/sec_statements_unit_context.py (same session)
retroactively confirmed SMMT's own real corruption - `_aggregate_concepts_resolve_entry_period`
had been mislabeling old-regime quarters into a permanent +1-year offset, producing garbage
fiscal_year=2026/2027 buckets (e.g. quarterly_income_statement period_end 2025-10-14,
2026-04-24, 2026-07-17 - all in fiscal_year rows that hadn't happened yet as of the fix
landing) with no revenue ever attached. NONE of the existing 17 DataPatrol checkers would ever
have caught this: tie_out.py/statistical_anomaly.py validate internal arithmetic/history
self-consistency (a garbage row with mismatched-but-internally-consistent NULLs doesn't trip
either), staleness.py checks elapsed time since the newest row was WRITTEN (not whether the
period it claims to cover has actually occurred), and financial_statement_flag_drift.py only
flags a row where EVERY required field is NULL AND data_unavailable=FALSE (a row with a real,
just stale/duplicate value in one field passes it, and 2 of SMMT's 3 garbage rows were already
correctly flagged data_unavailable=TRUE, which SKIPS that checker's own WHERE clause
entirely). A period that has not occurred yet is a defect independent of any of that - this
check is the missing piece.

FUTURE PERIOD_END (quarterly_income_statement only - the one financial-statement table with a
real period_end column; see this check's own docstring below for why the others use a
fiscal_year/quarter bound instead): any row where period_end is in the future is unconditionally
wrong - a quarter cannot be reported before it ends. Live-verified 2026-09-15: 2 hits (AAL FY2027
Q2 period_end 2027-07-17, MCAH FY2026 Q3 period_end 2026-09-30), both genuinely still in the
future as of this check's own live-run date.

FUTURE FISCAL_YEAR/QUARTER BOUND (all six statement tables, including quarterly_income_statement
as a belt-and-suspenders backstop): fiscal_year > this_year+1, OR fiscal_year == this_year+1 AND
fiscal_quarter >= 3. NOT a same-year-or-Q1/Q2-of-next-year bound - live-tested 2026-09-15 and
found genuinely noisy (1,250 real, correctly-populated rows for non-December-fiscal-year-end
filers whose real FY(this_year+1) Q1/Q2 has already occurred, e.g. ADSK/AEO/AAP). The
Q3/Q4-of-next-year bound clears every real filer in the live universe with zero false positives
(13 hits, quarterly_balance_sheet; 3, quarterly_cash_flow; 0, all three annual tables) - even a
filer with the most extreme practical non-December fiscal year end cannot have a real, filed
fiscal_year+1 Q3/Q4 by definition (that would require its fiscal year to already be MORE than a
year ahead of the calendar, which no real listed filer's fiscal calendar does).

Deliberately does NOT attempt to detect the harder "in-range but stale duplicate value carried
over from an unrelated period" corruption shape (e.g. SMMT's own 2026-Q3 total_assets=NULL/
stockholders_equity duplicated from FY2025-Q3) - live-tested 2026-09-15 via a cross-period
exact-value self-join and found it far too noisy to ship (repeated real values across adjacent
quarters for genuinely static small-cap balance sheet lines, e.g. AA/AAME/AARD, dominate any
real corruption signal). Flagged as a known open gap, not solved here - a future pass would
need a materially better discriminator than raw value equality before this is safe to add.
"""

import datetime
import logging
from typing import Any

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN

logger = logging.getLogger(__name__)

# Tables with no period_end column - checked via the fiscal_year/quarter bound only.
_FISCAL_BOUND_ONLY_TABLES: tuple[str, ...] = (
    "quarterly_balance_sheet",
    "quarterly_cash_flow",
    "annual_balance_sheet",
    "annual_income_statement",
    "annual_cash_flow",
)


class FinancialStatementPeriodSanityChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_future_period_end(cur)
        self.check_future_fiscal_year_quarter(cur)
        return self.results

    def check_future_period_end(self, cur: Any) -> None:
        """quarterly_income_statement.period_end in the future - unconditionally wrong,
        see this module's own docstring."""
        try:
            cur.execute(
                """
                SELECT symbol, fiscal_year, fiscal_quarter, period_end
                FROM quarterly_income_statement
                WHERE period_end > CURRENT_DATE
                ORDER BY period_end DESC
                LIMIT 50
                """
            )
            rows = cur.fetchall()
            if rows:
                samples = [
                    {
                        "symbol": r[0] if not isinstance(r, dict) else r.get("symbol"),
                        "fiscal_year": r[1] if not isinstance(r, dict) else r.get("fiscal_year"),
                        "fiscal_quarter": r[2] if not isinstance(r, dict) else r.get("fiscal_quarter"),
                        "period_end": str(r[3] if not isinstance(r, dict) else r.get("period_end")),
                    }
                    for r in rows[:10]
                ]
                self.log(
                    "financial_statement_period_sanity",
                    WARN,
                    "quarterly_income_statement",
                    f"{len(rows)} row(s) with period_end in the future - a quarter cannot be "
                    "reported before it ends, likely a fiscal-year-labeling bug (see "
                    "sec_statements_aggregate.py's cross-concept FYE conflict guard)",
                    {"count": len(rows), "samples": samples},
                )
            else:
                self.log(
                    "financial_statement_period_sanity",
                    INFO,
                    "quarterly_income_statement",
                    "no rows with a future period_end",
                )
        except Exception as e:
            logger.error(f"[FinancialStatementPeriodSanityChecker] future period_end check failed: {e}", exc_info=True)
            self.log("financial_statement_period_sanity", ERROR, "quarterly_income_statement", f"check failed: {e}")

    def check_future_fiscal_year_quarter(self, cur: Any) -> None:
        """fiscal_year/fiscal_quarter combo that cannot exist yet for any real filer's fiscal
        calendar - see this module's own docstring for the bound and why it's set where it is."""
        this_year = datetime.date.today().year
        for table in _FISCAL_BOUND_ONLY_TABLES:
            try:
                is_quarterly = table.startswith("quarterly_")
                params: tuple[int, ...]
                if is_quarterly:
                    where = "(fiscal_year > %s OR (fiscal_year = %s AND fiscal_quarter >= 3))"
                    params = (this_year + 1, this_year + 1)
                    select = "symbol, fiscal_year, fiscal_quarter"
                else:
                    where = "fiscal_year > %s"
                    params = (this_year + 1,)
                    select = "symbol, fiscal_year"
                cur.execute(
                    f"""
                    SELECT {select}
                    FROM {table}
                    WHERE {where}
                    ORDER BY fiscal_year DESC
                    LIMIT 50
                    """,
                    params,
                )
                rows = cur.fetchall()
                if rows:
                    samples = [
                        dict(
                            zip(
                                select.split(", "),
                                r if not isinstance(r, dict) else r.values(),
                                strict=True,
                            )
                        )
                        for r in rows[:10]
                    ]
                    self.log(
                        "financial_statement_period_sanity",
                        WARN,
                        table,
                        f"{len(rows)} row(s) with a fiscal_year/fiscal_quarter that cannot exist "
                        "yet for any real filer's fiscal calendar - likely a fiscal-year-labeling "
                        "bug (see sec_statements_aggregate.py's cross-concept FYE conflict guard)",
                        {"count": len(rows), "samples": samples},
                    )
                else:
                    self.log(
                        "financial_statement_period_sanity",
                        INFO,
                        table,
                        "no implausible future fiscal_year/fiscal_quarter rows",
                    )
            except Exception as e:
                logger.error(
                    f"[FinancialStatementPeriodSanityChecker] {table} fiscal-bound check failed: {e}", exc_info=True
                )
                self.log("financial_statement_period_sanity", ERROR, table, f"check failed: {e}")
