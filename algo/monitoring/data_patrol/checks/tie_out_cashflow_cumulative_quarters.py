"""Permanent DataPatrol guard for the cumulative-YTD-stored-as-discrete-quarter bug class,
mixed into TieOutChecker (tie_out.py) the same way every other tie_out_*.py mixin is.

ADDED 2026-09-13 (goal: keep finding data-quality issues, root-caused via RITM - see memory
quarterly_cashflow_cumulative_ytd_stored_as_discrete_20260913 for the full investigation and
utils/external/sec_statements_cumulative_quarter_derivation.py for the extraction-layer fix
that now prevents this going forward). That fix only applies to NEW extractions - existing
`quarterly_cash_flow` rows loaded before the fix (or a symbol simply not yet reloaded) can
still carry the bug's fingerprint, so this check exists to catch those, and to catch any
future regression of the extraction-layer fix itself (e.g. a new fallback concept added to
sec_cash_flow.py that isn't covered by the span-based derivation for some reason).

Detection signature (same one the original investigation used to quantify scope): a lone
same-fiscal-year cumulative XBRL fact stored as-is under Q2 and Q3 makes those two columns
come out IDENTICAL (Q2's H1 cumulative and Q3's 9mo cumulative only coincide when Q3's real
incremental activity is exactly zero - the common, expected case for a non-headline cash-flow
line item most quarters - but a Q1 value that's already different rules out "genuinely flat
whole year", since Q1 by itself is definitionally already-discrete and a real Q1-Q2-Q3-all-
equal figure would require zero activity in every quarter after Q1 too, an implausible
coincidence at scale).

Two variants, per field, confirmed against real SEC data for all 6 fields (see the memory
note above): `stock_based_compensation`/`common_stock_repurchased`/`capex`/`dividends_paid`
are non-negative by GAAP definition, so Q1 < Q2 == Q3 (both >= 0) is the tight, conservative
shape validated against RITM. `financing_cash_flow`/`investing_cash_flow` are real NET-flow
figures that are routinely negative (a company can genuinely have net cash USED in financing/
investing activities) - live-confirmed via ABEO (CIK 0000318306) FY2012/2020, both fields
negative throughout - so those two use Q1 != Q2 == Q3 instead, dropping the sign requirement
entirely; requiring Q1 != Q2 alone (regardless of sign) is still enough to rule out a
genuinely-flat year, since a real quarter-over-quarter change of exactly zero for 3 straight
quarters is the same implausible-coincidence argument as above.

FIXED 2026-09-13 (same-day follow-up, applied first to the auto-correcting sweep this check
pairs with - loaders/helpers/financial_statements_q4_sweeps.py's
`_sweep_correct_cumulative_ytd_field` - see that commit for the full story): this check never
joined annual_cash_flow or verified the quarters actually overshoot the annual total, so it
fired purely on the Q2==Q3 fingerprint above. Live-confirmed 8 real symbol/years (MA/APTV/
AGNC/ZTS and others, stock_based_compensation) have Q2==Q3 by genuine flat-accrual
coincidence with data that already reconciles exactly to the annual total - not a bug, just
flat quarter-over-quarter activity. Added the same `(q1+q2+q3) > annual` overshoot guard the
sweep uses, verified it still catches the check's own documented true positives (RITM/
Agilent's real pre-fix values both genuinely overshoot).
"""

import logging
from typing import TYPE_CHECKING, Any

from ..base import CheckResult
from ..config import INFO, WARN
from .tie_out_shared import _MAX_REPORTED_PER_CHECK

logger = logging.getLogger(__name__)

# Non-negative-by-GAAP-definition fields: Q1 < Q2 == Q3 (tight shape, RITM-validated).
_CUMULATIVE_PRONE_NONNEGATIVE_FIELDS = (
    "stock_based_compensation",
    "common_stock_repurchased",
    "capex",
    "dividends_paid",
)
# Net-flow fields that can be legitimately negative: Q1 != Q2 == Q3, no sign requirement -
# real-SEC-verified via ABEO (financing_cash_flow/investing_cash_flow both negative).
_CUMULATIVE_PRONE_NET_FLOW_FIELDS = (
    "financing_cash_flow",
    "investing_cash_flow",
)


class TieOutCashflowCumulativeQuartersMixin:
    if TYPE_CHECKING:
        results: list[CheckResult]

        def log(
            self,
            check_name: str,
            severity: str,
            target: str,
            message: str,
            details: dict[str, Any] | None = None,
        ) -> CheckResult: ...

    def check_quarterly_cashflow_cumulative_duplicate(self, cur: Any) -> None:
        """Flag Q2 == Q3 with Q1 different, per cash-flow field (sign-scoped, see module docstring)."""
        for field in _CUMULATIVE_PRONE_NONNEGATIVE_FIELDS:
            self._check_cumulative_duplicate_for_field(cur, field, sign_scoped=True)
        for field in _CUMULATIVE_PRONE_NET_FLOW_FIELDS:
            self._check_cumulative_duplicate_for_field(cur, field, sign_scoped=False)

    def _check_cumulative_duplicate_for_field(self, cur: Any, field: str, sign_scoped: bool) -> None:
        sign_clause = "AND q1.{f} >= 0 AND q2.{f} > 0 AND q1.{f} < q2.{f}" if sign_scoped else "AND q1.{f} != q2.{f}"
        try:
            cur.execute(
                f"""
                SELECT q1.symbol, q1.fiscal_year, q1.{field} AS q1_val, q2.{field} AS q2_val
                FROM quarterly_cash_flow q1
                JOIN quarterly_cash_flow q2
                    ON q2.symbol = q1.symbol AND q2.fiscal_year = q1.fiscal_year AND q2.fiscal_quarter = 2
                JOIN quarterly_cash_flow q3
                    ON q3.symbol = q1.symbol AND q3.fiscal_year = q1.fiscal_year AND q3.fiscal_quarter = 3
                JOIN annual_cash_flow a
                    ON a.symbol = q1.symbol AND a.fiscal_year = q1.fiscal_year
                JOIN stock_symbols s ON s.symbol = q1.symbol AND s.active = true
                WHERE q1.fiscal_quarter = 1
                  AND q1.data_unavailable = FALSE AND q2.data_unavailable = FALSE AND q3.data_unavailable = FALSE
                  AND a.data_unavailable = FALSE
                  AND q1.{field} IS NOT NULL AND q2.{field} IS NOT NULL AND q3.{field} IS NOT NULL
                  AND a.{field} IS NOT NULL
                  {sign_clause.format(f=field)}
                  AND q2.{field} = q3.{field}
                  AND (q1.{field} + q2.{field} + q3.{field}) > a.{field}
                """
            )
            rows = cur.fetchall()
            self._log_cumulative_duplicate_findings(field, rows)
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_cashflow_cumulative_duplicate_{field} failed: {e}", exc_info=True)

    def _log_cumulative_duplicate_findings(self, field: str, rows: Any) -> None:
        if not rows:
            # FIXED 2026-09-14 (goal: quarantine backlog session, same bug class as
            # tie_out_identity_quarterly.py's quarterly_revenue_sum_vs_annual_extreme):
            # this used to just `return` with no log call at all on a clean pass, so once a
            # flagged symbol's cumulative-duplicate signature got fixed, this check_name never
            # appeared in a patrol run's results again - and quarantine.py's
            # apply_symbol_quarantine only resolves a check_name's prior open symbol_quarantine
            # rows when that check_name is present in the CURRENT run's results (see
            # logger.py's log_results). Net effect: a symbol quarantined under
            # quarterly_cashflow_cumulative_duplicate_{field} stayed stuck "open" forever even
            # after its data was reloaded/fixed. Logging INFO unconditionally here mirrors every
            # other quarantine-eligible check in this package.
            self.log(
                f"quarterly_cashflow_cumulative_duplicate_{field}",
                INFO,
                "quarterly_cash_flow",
                f"no quarterly_cashflow_cumulative_duplicate_{field} violations found",
            )
            return
        flagged = [
            {
                "symbol": row["symbol"],
                "fiscal_year": row["fiscal_year"],
                "q1": float(row["q1_val"]),
                "q2_eq_q3": float(row["q2_val"]),
            }
            for row in rows
        ]
        flagged.sort(key=lambda r: r["symbol"])
        self.log(
            f"quarterly_cashflow_cumulative_duplicate_{field}",
            WARN,
            "quarterly_cash_flow",
            f"{len(flagged)} symbol/year(s) have {field} Q2 == Q3 with Q1 different - the "
            f"cumulative-YTD-stored-as-discrete-quarter signature (see "
            f"quarterly_cashflow_cumulative_ytd_stored_as_discrete_20260913 memory) - likely "
            f"predates the 2026-09-13 extraction-layer derivation fix and needs a reload",
            {
                "field": field,
                "count": len(flagged),
                "examples": flagged[:_MAX_REPORTED_PER_CHECK],
                "flagged_symbols": [{"symbol": r["symbol"], "reason": f"{field}_cumulative_q2_eq_q3"} for r in flagged],
            },
        )
