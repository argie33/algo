#!/usr/bin/env python3
"""Plausibility/hard-bound checks for scoring-adjacent metrics that had DataPatrol staleness
coverage but zero correctness/bounds coverage.

ADDED 2026-09-14 (goal: Yahoo-metric coverage sweep - cross-referencing the real Yahoo Finance
key-statistics/analysis/holders field set against our own schema and DataPatrol validation
found several CAPTURED-but-never-validated tables: `stability_metrics`, `positioning_metrics`,
`insider_transaction_velocity`, `growth_metrics`'s newer forward-looking fields, `dividend_data`,
`analyst_sentiment_analysis` - all had a staleness entry but nobody ever checked whether the
values themselves are even mathematically/statistically possible. Same "review queue, not silent
trust" philosophy as `score_ratio_outliers.py` and `specialized.py`'s RSI-bounds checks; per this
session's own re-confirmed rule (quarantine.py's deliberate fail-safe), every ERROR-severity
finding here identifies its own flagged_symbols so a bad row quarantines just that symbol
instead of halting the whole pipeline.

Two classes of bound used throughout, matching the ERROR-vs-WARN split this codebase already
uses elsewhere (see `score_ratio_outliers.py`'s own WARN/review-queue precedent):
- ERROR + flagged_symbols: a HARD, mathematically-impossible violation (a variance-based
  measure can't be negative, a percentage-of-shares can't be negative, an ownership percentage
  can't exceed 100%, a drawdown can't be positive or worse than -100%, a real stock price can't
  be <= 0). These are computation-error signatures, not judgment calls.
- WARN + flagged_symbols: a real, PLAUSIBLE-BUT-IMPLAUSIBLE value (an extreme beta, a >25%
  dividend yield, a >300% short-percent-of-float - genuinely possible in a real short squeeze,
  e.g. GameStop's 2021 float was shorted well over 100% - so this can't be a hard ERROR bound,
  but it's still worth a human glancing at it).
"""

import logging
from typing import Any

import psycopg2

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN

logger = logging.getLogger(__name__)

_MAX_FLAGGED_DETAIL = 20

# Same MAX_PLAUSIBLE_GROWTH_PCT convention already used for revenue_growth_1y/eps_growth_1y at
# write time (loaders/helpers/vqg_growth.py) - these 5 newer forward-looking/quarterly fields
# were added 2026-08-29/31 without the same guard, live-confirmed still stored as percentage
# units (e.g. DX's real fcf_growth_yoy=739.5%/quarterly_growth_momentum=140.35% are the
# precedent for "5-25x this bound is a real, already-seen corruption shape").
_MAX_PLAUSIBLE_GROWTH_PCT = 2000.0

_GROWTH_MAGNITUDE_FIELDS = (
    "forward_eps_growth_current_fy",
    "forward_eps_growth_next_fy",
    "forward_revenue_growth_next_fy",
    "sustainable_growth_rate",
    "quarterly_growth_momentum",
)


class MetricBoundsChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []

        checks = [
            ("stability_metrics_bounds", self.check_stability_metrics_bounds),
            ("positioning_metrics_bounds", self.check_positioning_metrics_bounds),
            ("insider_velocity_bounds", self.check_insider_velocity_bounds),
            ("growth_metrics_forward_field_magnitude", self.check_growth_metrics_forward_field_magnitude),
            ("dividend_data_bounds", self.check_dividend_data_bounds),
            ("analyst_sentiment_bounds", self.check_analyst_sentiment_bounds),
        ]
        for fn_name, fn in checks:
            sp = f"sp_mb_{fn_name}"
            try:
                cur.execute(f"SAVEPOINT {sp}")
            except psycopg2.DatabaseError as e:
                logger.critical(f"Database error creating SAVEPOINT {sp}: {e} - data patrol cannot proceed safely")
                self.log(fn_name, ERROR, fn_name, "SAVEPOINT creation failed - database state unknown", None)
                continue
            try:
                fn(cur)
            except Exception as e:
                logger.critical(f"MetricBounds {fn_name} check FAILED: {e} - results are incomplete")
                self.log(
                    fn_name, ERROR, fn_name, "Check execution failed - treating as critical failure", {"error": str(e)}
                )
            finally:
                try:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                except psycopg2.DatabaseError as e:
                    logger.warning(f"Failed to rollback SAVEPOINT {sp}: {e} - transaction state may be inconsistent")

        return self.results

    def _log_bound_violations(
        self,
        check_name: str,
        severity: str,
        table: str,
        field: str,
        rows: list[tuple[str, float]],
        reason: str,
        clean_message: str,
        total: int,
    ) -> None:
        if not rows:
            self.log(check_name, INFO, table, clean_message, {"total": total})
            return
        flagged_symbols = [{"symbol": s, "value": v, "reason": reason} for s, v in rows[:_MAX_FLAGGED_DETAIL] if s]
        self.log(
            check_name,
            severity,
            table,
            f"{len(rows)} row(s) with {field} outside plausible bounds: {reason}",
            {"count": len(rows), "flagged_symbols": flagged_symbols},
        )

    def check_stability_metrics_bounds(self, cur: Any) -> None:
        """volatility_*/downside_volatility_*/max_drawdown_1y are hard mathematical bounds
        (a variance-derived measure can't be negative; a drawdown can't be positive or worse
        than -100%). beta has no hard bound but a real equity's beta outside roughly [-5, 8]
        is implausible enough to warrant review (WARN, not ERROR - live-confirmed 27 such rows
        at add time, real leveraged/micro-float names, not necessarily bugs)."""
        cur.execute("SELECT COUNT(*) AS total FROM stability_metrics")
        row = cur.fetchone()
        total = int((row.get("total") if hasattr(row, "get") else row[0]) or 0)

        vol_fields = [
            "volatility_30d",
            "volatility_60d",
            "volatility_252d",
            "downside_volatility_30d",
            "downside_volatility_60d",
            "downside_volatility_252d",
        ]
        for field in vol_fields:
            cur.execute(f"""
                SELECT symbol, {field} AS val FROM stability_metrics
                WHERE {field} IS NOT NULL AND {field} < 0 AND COALESCE(data_unavailable, false) = false
            """)
            rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
            self._log_bound_violations(
                "stability_metrics_bounds",
                ERROR,
                "stability_metrics",
                field,
                rows,
                f"{field} < 0 is mathematically impossible for a variance-derived measure",
                f"{field} bounds valid ({total} rows)",
                total,
            )

        cur.execute("""
            SELECT symbol, max_drawdown_1y AS val FROM stability_metrics
            WHERE max_drawdown_1y IS NOT NULL
              AND (max_drawdown_1y > 0 OR max_drawdown_1y < -100)
              AND COALESCE(data_unavailable, false) = false
        """)
        rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
        self._log_bound_violations(
            "stability_metrics_bounds",
            ERROR,
            "stability_metrics",
            "max_drawdown_1y",
            rows,
            "max_drawdown_1y outside [-100, 0] is mathematically impossible (can't gain, can't lose more than 100%)",
            f"max_drawdown_1y bounds valid ({total} rows)",
            total,
        )

        cur.execute("""
            SELECT symbol, beta AS val FROM stability_metrics
            WHERE beta IS NOT NULL AND (beta < -5 OR beta > 8) AND COALESCE(data_unavailable, false) = false
        """)
        rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
        self._log_bound_violations(
            "stability_metrics_bounds",
            WARN,
            "stability_metrics",
            "beta",
            rows,
            "beta outside [-5, 8] is implausible for a real equity - review queue, not a confirmed bug",
            f"beta plausible for all rows ({total} rows)",
            total,
        )

    def check_positioning_metrics_bounds(self, cur: Any) -> None:
        """Ownership/short percentages can't be negative (hard bound, ERROR). Ownership
        percentages (institutional/top-10) can't exceed 100% - you can't own more than the
        whole company (hard bound, ERROR). Short-percent-of-float/shares CAN legitimately
        exceed 100% in a real short squeeze (e.g. GameStop 2021), so an upper bound there is a
        WARN plausibility check (>300%), not a hard ERROR. short_ratio (days-to-cover) can't
        be negative (hard bound, ERROR)."""
        cur.execute("SELECT COUNT(*) AS total FROM positioning_metrics")
        row = cur.fetchone()
        total = int((row.get("total") if hasattr(row, "get") else row[0]) or 0)

        hard_capped_pct_fields = ["institutional_ownership_pct", "top_10_institutions_pct"]
        for field in hard_capped_pct_fields:
            cur.execute(f"""
                SELECT symbol, {field} AS val FROM positioning_metrics
                WHERE {field} IS NOT NULL AND ({field} < 0 OR {field} > 100)
                  AND COALESCE(data_unavailable, false) = false
            """)
            rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
            self._log_bound_violations(
                "positioning_metrics_bounds",
                ERROR,
                "positioning_metrics",
                field,
                rows,
                f"{field} outside [0, 100] is mathematically impossible - can't own more than 100% of a company",
                f"{field} bounds valid ({total} rows)",
                total,
            )

        uncapped_pct_fields = ["short_interest_pct", "short_percent_of_float"]
        for field in uncapped_pct_fields:
            cur.execute(f"""
                SELECT symbol, {field} AS val FROM positioning_metrics
                WHERE {field} IS NOT NULL AND {field} < 0 AND COALESCE(data_unavailable, false) = false
            """)
            rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
            self._log_bound_violations(
                "positioning_metrics_bounds",
                ERROR,
                "positioning_metrics",
                field,
                rows,
                f"{field} < 0 is mathematically impossible for a percentage-of-shares measure",
                f"{field} non-negative for all rows ({total} rows)",
                total,
            )

            cur.execute(f"""
                SELECT symbol, {field} AS val FROM positioning_metrics
                WHERE {field} IS NOT NULL AND {field} > 300 AND COALESCE(data_unavailable, false) = false
            """)
            rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
            self._log_bound_violations(
                "positioning_metrics_bounds",
                WARN,
                "positioning_metrics",
                field,
                rows,
                f"{field} > 300% is extreme (a real short squeeze like GameStop 2021 can exceed 100%, "
                "but this is a review-queue candidate, not a confirmed bug)",
                f"{field} plausible for all rows ({total} rows)",
                total,
            )

        cur.execute("""
            SELECT symbol, short_ratio AS val FROM positioning_metrics
            WHERE short_ratio IS NOT NULL AND short_ratio < 0 AND COALESCE(data_unavailable, false) = false
        """)
        rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
        self._log_bound_violations(
            "positioning_metrics_bounds",
            ERROR,
            "positioning_metrics",
            "short_ratio",
            rows,
            "short_ratio (days-to-cover) < 0 is mathematically impossible",
            f"short_ratio non-negative for all rows ({total} rows)",
            total,
        )

    def check_insider_velocity_bounds(self, cur: Any) -> None:
        """buy_sell_ratio_30d/90d are ratios of non-negative transaction counts/shares, so a
        negative value is impossible (ERROR). insider_confidence_score is documented (see
        utils/external/sec_form345_transaction_velocity.py) as a 0-100 scale - a value outside
        that range is a construction bug, not a legitimate extreme (ERROR)."""
        cur.execute("SELECT COUNT(*) AS total FROM insider_transaction_velocity")
        row = cur.fetchone()
        total = int((row.get("total") if hasattr(row, "get") else row[0]) or 0)

        for field in ("buy_sell_ratio_30d", "buy_sell_ratio_90d"):
            cur.execute(f"""
                SELECT symbol, {field} AS val FROM insider_transaction_velocity
                WHERE {field} IS NOT NULL AND {field} < 0 AND COALESCE(data_unavailable, false) = false
            """)
            rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
            self._log_bound_violations(
                "insider_velocity_bounds",
                ERROR,
                "insider_transaction_velocity",
                field,
                rows,
                f"{field} < 0 is mathematically impossible for a ratio of non-negative transaction counts",
                f"{field} non-negative for all rows ({total} rows)",
                total,
            )

        cur.execute("""
            SELECT symbol, insider_confidence_score AS val FROM insider_transaction_velocity
            WHERE insider_confidence_score IS NOT NULL
              AND (insider_confidence_score < 0 OR insider_confidence_score > 100)
              AND COALESCE(data_unavailable, false) = false
        """)
        rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
        self._log_bound_violations(
            "insider_velocity_bounds",
            ERROR,
            "insider_transaction_velocity",
            "insider_confidence_score",
            rows,
            "insider_confidence_score outside [0, 100] violates its own documented 0-100 scale",
            f"insider_confidence_score bounds valid ({total} rows)",
            total,
        )

    def check_growth_metrics_forward_field_magnitude(self, cur: Any) -> None:
        """forward_eps_growth_current_fy/next_fy, forward_revenue_growth_next_fy,
        sustainable_growth_rate, quarterly_growth_momentum were added 2026-08-29/31 without
        the same MAX_PLAUSIBLE_GROWTH_PCT (2000%) write-time guard already applied to
        revenue_growth_1y/eps_growth_1y (loaders/helpers/vqg_growth.py) - a read-time WARN
        check here, since a magnitude this large is implausible but not a hard mathematical
        impossibility the way a negative variance is."""
        cur.execute("SELECT COUNT(*) AS total FROM growth_metrics")
        row = cur.fetchone()
        total = int((row.get("total") if hasattr(row, "get") else row[0]) or 0)

        for field in _GROWTH_MAGNITUDE_FIELDS:
            cur.execute(f"""
                SELECT symbol, {field} AS val FROM growth_metrics
                WHERE {field} IS NOT NULL AND ABS({field}) > {_MAX_PLAUSIBLE_GROWTH_PCT}
                  AND COALESCE(data_unavailable, false) = false
            """)
            rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
            self._log_bound_violations(
                "growth_metrics_forward_field_magnitude",
                WARN,
                "growth_metrics",
                field,
                rows,
                f"|{field}| > {_MAX_PLAUSIBLE_GROWTH_PCT:.0f}% is implausible - review queue, same threshold "
                "already used at write time for revenue_growth_1y/eps_growth_1y",
                f"{field} plausible for all rows ({total} rows)",
                total,
            )

    def check_dividend_data_bounds(self, cur: Any) -> None:
        """dividend_per_share/dividend_yield_pct < 0 is mathematically impossible (ERROR).
        dividend_yield_pct > 25% is possible (deep-value/distressed names) but rare enough to
        be worth a review-queue WARN, matching the same "high-yield is a real but reviewable
        case" philosophy score_ratio_outliers.py already uses for fcf_yield."""
        cur.execute("SELECT COUNT(*) AS total FROM dividend_data")
        row = cur.fetchone()
        total = int((row.get("total") if hasattr(row, "get") else row[0]) or 0)

        for field in ("dividend_per_share", "dividend_yield_pct"):
            cur.execute(f"""
                SELECT symbol, {field} AS val FROM dividend_data
                WHERE {field} IS NOT NULL AND {field} < 0 AND COALESCE(data_unavailable, false) = false
            """)
            rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
            self._log_bound_violations(
                "dividend_data_bounds",
                ERROR,
                "dividend_data",
                field,
                rows,
                f"{field} < 0 is mathematically impossible for a dividend payment/yield",
                f"{field} non-negative for all rows ({total} rows)",
                total,
            )

        cur.execute("""
            SELECT symbol, dividend_yield_pct AS val FROM dividend_data
            WHERE dividend_yield_pct IS NOT NULL AND dividend_yield_pct > 25
              AND COALESCE(data_unavailable, false) = false
        """)
        rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
        self._log_bound_violations(
            "dividend_data_bounds",
            WARN,
            "dividend_data",
            "dividend_yield_pct",
            rows,
            "dividend_yield_pct > 25% is rare/suspicious (real but reviewable, e.g. a distressed payer "
            "about to cut) - review queue, not a confirmed bug",
            f"dividend_yield_pct plausible for all rows ({total} rows)",
            total,
        )

    def check_analyst_sentiment_bounds(self, cur: Any) -> None:
        """target_price <= 0 is mathematically impossible for a real analyst price target
        (ERROR). upside_downside_percent has no hard bound but a magnitude beyond 500% is
        implausible enough to review (WARN)."""
        cur.execute("SELECT COUNT(*) AS total FROM analyst_sentiment_analysis")
        row = cur.fetchone()
        total = int((row.get("total") if hasattr(row, "get") else row[0]) or 0)

        cur.execute("""
            SELECT symbol, target_price AS val FROM analyst_sentiment_analysis
            WHERE target_price IS NOT NULL AND target_price <= 0
              AND COALESCE(data_unavailable, false) = false
        """)
        rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
        self._log_bound_violations(
            "analyst_sentiment_bounds",
            ERROR,
            "analyst_sentiment_analysis",
            "target_price",
            rows,
            "target_price <= 0 is mathematically impossible for a real analyst price target",
            f"target_price positive for all rows ({total} rows)",
            total,
        )

        cur.execute("""
            SELECT symbol, upside_downside_percent AS val FROM analyst_sentiment_analysis
            WHERE upside_downside_percent IS NOT NULL AND ABS(upside_downside_percent) > 500
              AND COALESCE(data_unavailable, false) = false
        """)
        rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
        self._log_bound_violations(
            "analyst_sentiment_bounds",
            WARN,
            "analyst_sentiment_analysis",
            "upside_downside_percent",
            rows,
            "|upside_downside_percent| > 500% is implausible - review queue, not a confirmed bug",
            f"upside_downside_percent plausible for all rows ({total} rows)",
            total,
        )
