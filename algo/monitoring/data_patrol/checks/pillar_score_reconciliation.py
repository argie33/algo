#!/usr/bin/env python3
"""Verifies stock_scores pillar columns reconcile to their own authoritative source tables.

Added 2026-09-08 (goal: score sanity audit, follow-up to composite_score_reconciliation.py).
That module closed the gap between composite_score and its 5 stored pillar inputs, but nothing
verified the pillar layer ITSELF against the table each pillar is actually computed from and
copied out of. For Quality specifically: quality_metrics.quality_score is the sole authoritative
value (see loaders/stock_scores/quality_scoring.py's _score_quality - "Uses only pre-computed
quality_score... No fallback computation"), and stock_scores.quality_score is a straight copy of
it (loaders/load_stock_scores.py's batch load path). A stale stock_scores row - built before a
quality_metrics rewrite/backfill/reload, or a copy bug - would silently diverge with nothing in
CI to catch it. This is exactly the failure mode live-observed in this same session: a landed-
but-not-yet-reloaded quality_metrics fix (broker-dealer fcf_margin exclusion) leaves stock_scores
holding stale GS/MS quality_score values with no automated signal that a reload is needed.

Deliberately does NOT re-derive quality_score from raw ratio columns (roe/roa/roce_pct/
fcf_margin/debt_to_equity/margin_volatility/asset_turnover/gross_profitability) via the
sector-neutral z-score formula itself - that formula lives in
loaders/helpers/vqg_quality_batch.py's update_quality_sector_neutral_scores() and is under
active concurrent development in this session (broker-dealer exclusion set, D2E/ROA/ROCE peer-
group refinement). Duplicating that logic here would (a) violate reuse-over-reimplementation for
a formula still in flux, and (b) risk flagging every symbol as a false positive the moment a
legitimate methodology change lands in one copy but not the other. update_quality_sector_neutral_
scores() already self-heals quality_metrics.quality_score against the raw ratios on every batch
run (it's a pure overwrite, not additive-delta) - the real, previously-uncovered gap is one layer
up: does stock_scores actually hold what quality_metrics currently says. That's what this checks.

Given its own new module for the same file-size-ratchet reason composite_score_reconciliation.py
was: tie_out.py is already past its size-ratchet ceiling.
"""

import logging
from typing import Any

from ..base import BaseCheck, CheckResult
from ..config import ERROR, WARN

logger = logging.getLogger(__name__)

_MAX_REPORTED_PER_CHECK = 20
_WARN_ABS = 0.01  # float/rounding noise budget - both columns store the same numeric(5,2) shape
_ERROR_ABS = 1.0  # beyond this is not explainable by rounding - a stale copy or a real bug


class PillarScoreReconciliationChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_quality_score_reconciliation(cur)
        return self.results

    def check_quality_score_reconciliation(self, cur: Any) -> None:
        try:
            cur.execute(
                """
                SELECT ss.symbol, ss.date, ss.quality_score AS stock_scores_quality_score,
                       qm.quality_score AS quality_metrics_quality_score
                FROM (
                    SELECT DISTINCT ON (symbol) symbol, date, quality_score
                    FROM stock_scores
                    WHERE quality_score IS NOT NULL
                    ORDER BY symbol, date DESC
                ) ss
                JOIN quality_metrics qm ON qm.symbol = ss.symbol
                WHERE qm.quality_score IS NOT NULL
                  AND COALESCE(qm.data_unavailable, false) = false
                """
            )
            flagged = []
            for row in cur.fetchall():
                stored = float(row["stock_scores_quality_score"])
                source = float(row["quality_metrics_quality_score"])
                divergence = abs(stored - source)
                if divergence > _WARN_ABS:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "date": str(row["date"]),
                            "stock_scores_quality_score": stored,
                            "quality_metrics_quality_score": source,
                            "divergence": round(divergence, 4),
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["divergence"], reverse=True)
                severity = ERROR if flagged[0]["divergence"] > _ERROR_ABS else WARN
                self.log(
                    "pillar_score_reconciliation",
                    severity,
                    "stock_scores",
                    f"{len(flagged)} symbol(s) have a stock_scores.quality_score that doesn't "
                    f"match its own authoritative source (quality_metrics.quality_score) beyond "
                    f"a {_WARN_ABS}-point rounding budget (max divergence "
                    f"{flagged[0]['divergence']:.4f}) - likely a stale stock_scores row awaiting "
                    f"reload after a quality_metrics recompute/backfill",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(
                f"[PillarScoreReconciliationChecker] check_quality_score_reconciliation failed: {e}", exc_info=True
            )
            self.log(
                "pillar_score_reconciliation",
                ERROR,
                "stock_scores",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )
