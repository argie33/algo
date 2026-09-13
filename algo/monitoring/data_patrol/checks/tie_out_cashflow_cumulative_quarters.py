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
line item most quarters - but a Q1 value that's already smaller rules out "genuinely flat
whole year", since Q1 by itself is definitionally already-discrete and a real Q1-Q2-Q3-all-
equal figure would require zero activity in every quarter after Q1 too, an implausible
coincidence at scale). Scoped to Q1 < Q2 == Q3 (Q1 present and non-negative) to keep the same
conservative shape validated against RITM in the original investigation.
"""

import logging
from typing import TYPE_CHECKING, Any

from ..base import CheckResult
from ..config import WARN
from .tie_out_shared import _MAX_REPORTED_PER_CHECK

logger = logging.getLogger(__name__)

# The 6 non-headline cash-flow-statement line items the original investigation confirmed
# carrying this signature at scale (operating_cash_flow is deliberately excluded - it almost
# always gets a real discrete fact filed, being a prominent headline number, and was only 88
# symbols vs hundreds-to-1,800+ for these).
_CUMULATIVE_PRONE_CASHFLOW_FIELDS = (
    "stock_based_compensation",
    "common_stock_repurchased",
    "capex",
    "financing_cash_flow",
    "investing_cash_flow",
    "dividends_paid",
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
        """Flag Q1 < Q2 == Q3 (all present, Q1/Q2 non-negative) per cash-flow field."""
        for field in _CUMULATIVE_PRONE_CASHFLOW_FIELDS:
            try:
                cur.execute(
                    f"""
                    SELECT q1.symbol, q1.fiscal_year, q1.{field} AS q1_val, q2.{field} AS q2_val
                    FROM quarterly_cash_flow q1
                    JOIN quarterly_cash_flow q2
                        ON q2.symbol = q1.symbol AND q2.fiscal_year = q1.fiscal_year AND q2.fiscal_quarter = 2
                    JOIN quarterly_cash_flow q3
                        ON q3.symbol = q1.symbol AND q3.fiscal_year = q1.fiscal_year AND q3.fiscal_quarter = 3
                    JOIN stock_symbols s ON s.symbol = q1.symbol AND s.active = true
                    WHERE q1.fiscal_quarter = 1
                      AND q1.data_unavailable = FALSE AND q2.data_unavailable = FALSE AND q3.data_unavailable = FALSE
                      AND q1.{field} IS NOT NULL AND q2.{field} IS NOT NULL AND q3.{field} IS NOT NULL
                      AND q1.{field} >= 0 AND q2.{field} > 0
                      AND q1.{field} < q2.{field}
                      AND q2.{field} = q3.{field}
                    """
                )
                rows = cur.fetchall()
                if not rows:
                    continue
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
                    f"{len(flagged)} symbol/year(s) have {field} Q2 == Q3 with Q1 strictly "
                    f"smaller - the cumulative-YTD-stored-as-discrete-quarter signature "
                    f"(see quarterly_cashflow_cumulative_ytd_stored_as_discrete_20260913 memory) "
                    f"- likely predates the 2026-09-13 extraction-layer derivation fix and "
                    f"needs a reload",
                    {
                        "field": field,
                        "count": len(flagged),
                        "examples": flagged[:_MAX_REPORTED_PER_CHECK],
                        "flagged_symbols": [
                            {"symbol": r["symbol"], "reason": f"{field}_cumulative_q2_eq_q3"} for r in flagged
                        ],
                    },
                )
            except Exception as e:
                logger.error(
                    f"[TieOutChecker] quarterly_cashflow_cumulative_duplicate_{field} failed: {e}", exc_info=True
                )
