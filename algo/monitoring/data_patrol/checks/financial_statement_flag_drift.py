#!/usr/bin/env python3
"""Detects financial-statement rows stuck data_unavailable=FALSE/reason=NULL with every
required field NULL - the same "available-but-empty" bug class
scripts/fix_stuck_available_but_null_financial_statement_flags.py retroactively corrected
2026-09-10.

BACKGROUND: load_financial_statements.py's post_run() (2026-09-02/09-03 fix, see that
method's own docstring) force-nulls a row's required field(s) when this run's fetch can't
trust the filer's value, then syncs data_unavailable/reason to match - but ONLY for rows
THIS run's own force-null loop touches. A row force-nulled by an older run, before that fix
existed, or by any future code path that force-nulls a value without going through
post_run()'s sync, is left at whatever a prior successful run wrote (almost always
FALSE/NULL) and silently looks "available" to every `WHERE data_unavailable = FALSE` reader
(the coverage report, quality/growth/value metrics' reason-chain checks) forever, unless
some later run happens to re-fetch and re-transform() that exact fiscal year.

The one-time script above fixed every row stuck this way as of 2026-09-10. This check is
the "make sure it doesn't silently pile back up between then and whenever a human next
remembers to look" companion - same relationship as xbrl_new_concepts.py has to
scripts/xbrl_concept_coverage_scan.py: the script remains the right tool for a deliberate
deep dive (and for actually fixing anything this finds), this just makes sure a human hears
about it automatically on the next scheduled DataPatrol pass instead of only when someone
happens to re-run the script by hand.

Deliberately WARN, not ERROR/CRIT: a stuck row is a real data-quality defect worth fixing,
but not a live-trading-safety issue on its own (same class of severity as xbrl_new_concepts'
undismissed-concept finding) - it silently degrades data-coverage reporting/gap analysis,
it does not corrupt a price, a score, or an order.
"""

import logging
from typing import Any

from ..base import BaseCheck, CheckResult
from ..config import ERROR, WARN

logger = logging.getLogger(__name__)

# table -> required fields, mirroring load_financial_statements.py's own
# _REQUIRED_STATEMENT_FIELDS (duplicated rather than imported: importing
# load_financial_statements.py here would pull in its whole loader-setup import chain -
# setup_imports()/terraform-env-var config/SecEdgarClient construction - into every
# DataPatrol run, for six field names that essentially never change; the loader's own
# tests already guard _REQUIRED_STATEMENT_FIELDS's real values, and the one-time script
# above documents the same duplication trade-off wasn't made - it imports the loader
# directly since it's a deliberate one-off invocation, not a hot per-pipeline-pass path).
_REQUIRED_FIELDS_BY_TABLE: dict[str, tuple[str, ...]] = {
    "annual_balance_sheet": ("total_assets", "stockholders_equity"),
    "annual_income_statement": ("revenue", "net_income"),
    "annual_cash_flow": ("operating_cash_flow",),
    "quarterly_balance_sheet": ("total_assets", "stockholders_equity"),
    "quarterly_income_statement": ("revenue", "net_income"),
    "quarterly_cash_flow": ("operating_cash_flow",),
}

_WARN_THRESHOLD = 1


class FinancialStatementFlagDriftChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_stuck_available_but_null_rows(cur)
        return self.results

    def check_stuck_available_but_null_rows(self, cur: Any) -> None:
        for table, required_fields in _REQUIRED_FIELDS_BY_TABLE.items():
            try:
                null_clause = " AND ".join(f"{f} IS NULL" for f in required_fields)
                cur.execute(
                    f"""
                    SELECT COUNT(*), COUNT(DISTINCT symbol)
                    FROM {table}
                    WHERE data_unavailable = FALSE AND reason IS NULL AND {null_clause}
                    """
                )
                row = cur.fetchone()
                row_count = int(row[0]) if row and row[0] is not None else 0
                symbol_count = int(row[1]) if row and row[1] is not None else 0
                if row_count >= _WARN_THRESHOLD:
                    self.log(
                        "financial_statement_flag_drift",
                        WARN,
                        table,
                        f"{row_count} row(s) across {symbol_count} symbol(s) are stuck "
                        "data_unavailable=FALSE/reason=NULL with every required field NULL "
                        "(available-but-empty) - see "
                        "scripts/fix_stuck_available_but_null_financial_statement_flags.py",
                        {"row_count": row_count, "symbol_count": symbol_count},
                    )
            except Exception as e:
                logger.error(f"[FinancialStatementFlagDriftChecker] {table} check failed: {e}", exc_info=True)
                self.log(
                    "financial_statement_flag_drift",
                    ERROR,
                    table,
                    f"check failed: {e}",
                )
