#!/usr/bin/env python3
"""Statistical (magnitude vs. own trailing history) anomaly detection for XBRL-extracted data.

Added 2026-09-07 (goal session: "is there a better way to deal with XBRL validation" ->
follow-up "build out everything we want"). tie_out.py's checks are all strict arithmetic
identities (Assets == Liabilities + Equity, etc.) - they catch extraction bugs that violate
GAAP arithmetic, but say nothing about a value that is internally self-consistent yet
implausible relative to the same symbol's own recent history (e.g. a magnitude/scale bug that
happens to not break any identity, or a concept-priority bug that picks a real but wrong-period
value). This is the "statistical peer/history deviation" layer real data vendors use to route a
review queue instead of hand-checking every symbol - see
[[xbrl_new_concept_automation_landed_20260907]] in memory for the fuller writeup of what
vendors do and why this was the next-highest-leverage piece to add here.

Deliberately WARN, not ERROR/CRIT, and deliberately framed as "go look at this" rather than
"this is a bug": a live feasibility scan against the local DB (2026-09-07) confirmed genuine,
large, real-economics-driven YoY swings exist at exactly this magnitude - QXO's revenue went
$56.9M -> $6.84B (2025, a real roll-up acquisition spree), several biotechs go from ~$0 to
material revenue on a single drug approval/licensing deal, and reverse cases exist too (TIPT
$341M -> $488K, a real divestiture). A magnitude check can never distinguish "real event" from
"extraction bug" on its own the way a strict identity check can - it can only say "this is far
outside the normal range, someone should look." Thresholds (20x growth / 0.05x shrinkage, $1M
floor to exclude sub-materiality small-cap noise) were tuned against the live DB: p95 of the
YoY ratio distribution for both revenue and total_assets is ~2.2x, so 20x sits far outside
normal variance while still catching a real, bounded population (67/4,443 revenue rows with the
floor applied) rather than flagging routine year-over-year noise.

This does NOT replace tie_out.py's identity checks (an identity violation is definitively wrong
by construction; a magnitude swing merely needs a human to confirm which case it is) - the two
are complementary layers, matching how real vendors combine deterministic arithmetic validation
with statistical outlier routing rather than relying on either alone.

Extended 2026-09-09 (goal session: "are we actually catching weird values") from revenue/
total_assets only to every other field tie_out.py already reads off the same three tables
(gross_profit, net_income, operating_income, pretax_income, total_liabilities,
stockholders_equity, operating_cash_flow) via the same generic _yoy_magnitude_jump helper -
same threshold, same floor, no new query pattern. The prior 2-field scope wasn't a deliberate
design choice, just what got built first.
"""

import logging
from typing import Any

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN

logger = logging.getLogger(__name__)

# Live feasibility check against the local DB (2026-09-07): p50/p90/p95/p99 of the YoY
# abs-value ratio for both revenue and total_assets is 1.05-2.2x/8-12x/well under 20x - a 20x
# threshold sits far outside normal variance. The $1M floor on the LARGER of the two years
# excludes small-cap/pre-revenue noise (a company going from $10K to $300K revenue is a 30x
# ratio but immaterial in dollar terms, not worth a review-queue entry).
_MAGNITUDE_JUMP_RATIO = 20.0
_MAGNITUDE_JUMP_FLOOR = 1_000_000.0
_MAX_REPORTED_PER_CHECK = 20


class StatisticalAnomalyChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_revenue_yoy_magnitude_jump(cur)
        self.check_total_assets_yoy_magnitude_jump(cur)
        self.check_gross_profit_yoy_magnitude_jump(cur)
        self.check_net_income_yoy_magnitude_jump(cur)
        self.check_operating_income_yoy_magnitude_jump(cur)
        self.check_pretax_income_yoy_magnitude_jump(cur)
        self.check_total_liabilities_yoy_magnitude_jump(cur)
        self.check_stockholders_equity_yoy_magnitude_jump(cur)
        self.check_operating_cash_flow_yoy_magnitude_jump(cur)
        return self.results

    def _yoy_magnitude_jump(
        self,
        cur: Any,
        check_name: str,
        table: str,
        field: str,
    ) -> None:
        try:
            # FIXED 2026-09-13 (goal: patrol/quarantine comprehensiveness audit): this used to
            # pick only each symbol's single LATEST fiscal year via `DISTINCT ON (symbol) ...
            # ORDER BY fiscal_year DESC`, then join that one year to fiscal_year - 1 - so a
            # magnitude jump in any OLDER fiscal-year transition was permanently invisible, the
            # same "narrow scope misses historical corruption" bug class already fixed in
            # ohlc_sanity (quality.py). These tables get populated via historical backfills
            # (many past fiscal years loaded at once), so an old-year jump may never have been
            # "latest" at the moment it actually happened. Live-verified: reproducing this same
            # logic across ALL adjacent fiscal-year pairs (not just each symbol's latest) found
            # 15 real anomalous jumps this check could never surface, e.g. UK FY2017->FY2018
            # revenue $99.31 -> $65.2M (656,640x) and HL FY2010->FY2011 $126,000 -> $477.6M -
            # several of the prior-year values look like unit/scale extraction bugs, exactly
            # what this checker exists to catch. Now joins every (year, year-1) pair directly
            # instead of restricting to the latest year first.
            cur.execute(
                f"""
                SELECT a.symbol, a.fiscal_year,
                       a.{field} AS curr_value, b.{field} AS prior_value
                FROM {table} a
                JOIN stock_symbols s ON s.symbol = a.symbol AND s.active = true
                JOIN {table} b ON b.symbol = a.symbol AND b.fiscal_year = a.fiscal_year - 1
                WHERE a.data_unavailable = FALSE AND a.{field} IS NOT NULL AND a.{field} != 0
                  AND b.data_unavailable = FALSE AND b.{field} IS NOT NULL AND b.{field} != 0
                """
            )
            flagged = []
            for row in cur.fetchall():
                curr_value, prior_value = float(row["curr_value"]), float(row["prior_value"])
                if max(abs(curr_value), abs(prior_value)) < _MAGNITUDE_JUMP_FLOOR:
                    continue
                ratio = abs(curr_value) / abs(prior_value)
                if ratio > _MAGNITUDE_JUMP_RATIO or ratio < (1.0 / _MAGNITUDE_JUMP_RATIO):
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "prior_value": prior_value,
                            "curr_value": curr_value,
                            "ratio": round(ratio, 4),
                        }
                    )
            if flagged:
                # ratio is rounded to 4dp for the report; an extreme-enough shrinkage (e.g.
                # $1 vs $8.18B, JMKE total_assets, found 2026-09-09) rounds to 0.0000, and
                # 1.0/0.0 would raise - a rounded-to-zero ratio is the most severe case, so
                # sort it as effectively infinite rather than dividing by it.
                flagged.sort(
                    key=lambda r: (
                        r["ratio"] if r["ratio"] > 1 else (1.0 / r["ratio"] if r["ratio"] > 0 else float("inf"))
                    ),
                    reverse=True,
                )
                self.log(
                    check_name,
                    WARN,
                    table,
                    f"{len(flagged)} symbol/year(s) show a >{_MAGNITUDE_JUMP_RATIO:.0f}x YoY swing in "
                    f"{field} (floor ${_MAGNITUDE_JUMP_FLOOR:,.0f}) - review queue, not a confirmed bug: "
                    "real M&A/divestiture/pre-revenue events can produce swings this large",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
            else:
                # Always log even when clean (FIXED 2026-09-10, see
                # pillar_score_reconciliation.py's identical fix for the full rationale): a
                # silent no-op here can never supersede/resolve an earlier flagged finding for
                # this same check_name still marked 'open' in data_patrol_log.
                self.log(check_name, INFO, table, f"no >{_MAGNITUDE_JUMP_RATIO:.0f}x YoY swing in {field}")
        except Exception as e:
            logger.error(f"[StatisticalAnomalyChecker] {check_name} failed: {e}", exc_info=True)
            self.log(check_name, ERROR, table, f"{check_name} failed: {e}")

    def check_revenue_yoy_magnitude_jump(self, cur: Any) -> None:
        self._yoy_magnitude_jump(cur, "revenue_yoy_magnitude_jump", "annual_income_statement", "revenue")

    def check_total_assets_yoy_magnitude_jump(self, cur: Any) -> None:
        self._yoy_magnitude_jump(cur, "total_assets_yoy_magnitude_jump", "annual_balance_sheet", "total_assets")

    def check_gross_profit_yoy_magnitude_jump(self, cur: Any) -> None:
        self._yoy_magnitude_jump(cur, "gross_profit_yoy_magnitude_jump", "annual_income_statement", "gross_profit")

    def check_net_income_yoy_magnitude_jump(self, cur: Any) -> None:
        self._yoy_magnitude_jump(cur, "net_income_yoy_magnitude_jump", "annual_income_statement", "net_income")

    def check_operating_income_yoy_magnitude_jump(self, cur: Any) -> None:
        self._yoy_magnitude_jump(
            cur, "operating_income_yoy_magnitude_jump", "annual_income_statement", "operating_income"
        )

    def check_pretax_income_yoy_magnitude_jump(self, cur: Any) -> None:
        self._yoy_magnitude_jump(cur, "pretax_income_yoy_magnitude_jump", "annual_income_statement", "pretax_income")

    def check_total_liabilities_yoy_magnitude_jump(self, cur: Any) -> None:
        self._yoy_magnitude_jump(
            cur, "total_liabilities_yoy_magnitude_jump", "annual_balance_sheet", "total_liabilities"
        )

    def check_stockholders_equity_yoy_magnitude_jump(self, cur: Any) -> None:
        self._yoy_magnitude_jump(
            cur, "stockholders_equity_yoy_magnitude_jump", "annual_balance_sheet", "stockholders_equity"
        )

    def check_operating_cash_flow_yoy_magnitude_jump(self, cur: Any) -> None:
        self._yoy_magnitude_jump(
            cur, "operating_cash_flow_yoy_magnitude_jump", "annual_cash_flow", "operating_cash_flow"
        )
