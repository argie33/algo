#!/usr/bin/env python3
"""Surfaces actively-scored symbols whose Quality/Value/Growth pillars are currently built on a
CONFIRMED, unfixed XBRL extraction bug.

Added 2026-09-19 (/goal "we can only be confident in our scores if we are confident in our
data" session). scripts/xbrl_yfinance_crosscheck.py and its sibling scripts populate
xbrl_yfinance_line_item_report with a `review_status` per (symbol, field, fiscal_year): most
rows are `unreviewed` (a raw divergence vs. yfinance, not yet individually verified against the
actual SEC filing - NOT proof of a bug, since many close `reviewed_not_error` after a human/
agent traces the real concept), but `reviewed_needs_fix` means someone already did that tracing
and confirmed it's a real, root-caused extraction bug that just hasn't been landed in code or
patched in the DB yet (see this session's own COP/PSX operating_income and AAOI long_term_debt
fixes for concrete examples of exactly this state existing, silently, for real symbols).

Nothing anywhere in this pipeline surfaced that gap before now: `reviewed_needs_fix` sat in a
review-tool table that nothing else reads, while stock_scores kept computing Quality/Value/
Growth off the same known-bad raw fundamentals, with no signal to a human that any individual
score might currently rest on a confirmed error. This check closes that gap - it does not fix
the underlying rows (each one needs its own individually-verified correction, per this
session's whole `/goal` mandate against blind pattern-fixes) and it does not touch the score
formula itself (that would risk exactly the kind of "blind pattern-apply corrupts other
filers" failure this codebase's history repeatedly warns about) - it only makes the existing,
already-confirmed risk visible on every patrol run instead of requiring someone to remember to
query xbrl_yfinance_line_item_report by hand.

WARN, not ERROR/CRIT: a `reviewed_needs_fix` row is a known, bounded, already-triaged issue (not
an unexplained anomaly) and typically affects one or two fiscal years of one field, not a
symbol's entire score - same severity judgment as xbrl_new_concepts.py's "go look at this, not
proof of a live crisis" WARN. Restricted to symbols that actually have a current stock_scores
row (no point alerting on a fundamentals bug for a symbol that isn't being scored at all) and to
the three fundamentals tables that feed Value/Growth/Quality (annual_balance_sheet/
annual_cash_flow/annual_income_statement - quarterly tables and other statement types aren't
scored inputs here).
"""

import logging
from typing import Any

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN

logger = logging.getLogger(__name__)

_MAX_REPORTED = 20
_SCORED_FUNDAMENTALS_TABLES = ("annual_balance_sheet", "annual_cash_flow", "annual_income_statement")


class ConfirmedXbrlBugScoreExposureChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_confirmed_bug_score_exposure(cur)
        return self.results

    def check_confirmed_bug_score_exposure(self, cur: Any) -> None:
        try:
            cur.execute(
                """
                SELECT r.symbol, r.our_table, r.our_field, r.fiscal_year, r.review_note
                FROM xbrl_yfinance_line_item_report r
                WHERE r.review_status = 'reviewed_needs_fix'
                  AND r.our_table = ANY(%(tables)s)
                  AND EXISTS (
                      SELECT 1 FROM stock_scores ss
                      WHERE ss.symbol = r.symbol
                        AND (ss.quality_score IS NOT NULL OR ss.value_score IS NOT NULL OR ss.growth_score IS NOT NULL)
                  )
                ORDER BY r.symbol, r.our_table, r.our_field, r.fiscal_year
                """,
                {"tables": list(_SCORED_FUNDAMENTALS_TABLES)},
            )
            rows = cur.fetchall()
            if not rows:
                # Always log even when clean - see pillar_score_reconciliation.py's identical
                # fix for the full rationale (a silent return can never resolve an earlier
                # flagged finding still marked 'open' in data_patrol_log).
                self.log(
                    "confirmed_xbrl_bug_score_exposure",
                    INFO,
                    "stock_scores",
                    "no currently-scored symbol has a confirmed (reviewed_needs_fix), unfixed "
                    "XBRL extraction bug in its fundamentals",
                )
                return
            symbols = sorted({row["symbol"] for row in rows})
            examples = [
                {
                    "symbol": row["symbol"],
                    "table": row["our_table"],
                    "field": row["our_field"],
                    "fiscal_year": row["fiscal_year"],
                    "note": row["review_note"],
                }
                for row in rows[:_MAX_REPORTED]
            ]
            self.log(
                "confirmed_xbrl_bug_score_exposure",
                WARN,
                "stock_scores",
                f"{len(symbols)} currently-scored symbol(s) ({len(rows)} field/year row(s)) have "
                "a CONFIRMED, unfixed XBRL extraction bug (review_status=reviewed_needs_fix) in "
                "a fundamentals field feeding Value/Growth/Quality - see "
                "xbrl_yfinance_line_item_report for the full list",
                {"symbol_count": len(symbols), "row_count": len(rows), "symbols": symbols, "examples": examples},
            )
        except Exception as e:
            logger.error(
                f"[ConfirmedXbrlBugScoreExposureChecker] check_confirmed_bug_score_exposure failed: {e}",
                exc_info=True,
            )
            self.log(
                "confirmed_xbrl_bug_score_exposure",
                ERROR,
                "stock_scores",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )
