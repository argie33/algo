#!/usr/bin/env python3
"""Verifies composite_score reconciles to its own pillar inputs.

Added 2026-09-08 (goal: score sanity audit). tie_out.py's ~76-108 checks all operate on raw
financial-statement fields (balance sheet identities, cash flow reconciliation) or on individual
ratio inputs (score_ratio_outliers.py). None of them verify the pillar-score layer itself: that
a symbol's stored composite_score actually equals what loaders/load_stock_scores.py's
_compute_stock_score would produce from that same row's 5 pillar scores. A real weighting or
arithmetic bug of meaningful size (a stale hand-copied weight, a skipped interaction term) would
currently reach production undetected.

Given its own new module (not added to tie_out.py) because that file is already past its
800-line-equivalent size-ratchet ceiling and cannot take new checks - see
.file-size-baseline.json's note on tie_out.py.

This is an EXACT recompute, not a tolerance-banded check like tie_out.py's siblings: fixed
BASE_PILLAR_WEIGHTS, adjusted only by _value_risk_adjusted_weights' deterministic value<->risk
weight transfer (conditioned on the symbol's own risk_score), with a missing pillar contributing
0 (no redistribution, per GOVERNANCE). The only legitimate slack is float/rounding noise.
"""

import logging
from typing import Any

from loaders.stock_scores.pillar_weights import _value_risk_adjusted_weights

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN

logger = logging.getLogger(__name__)

_MAX_REPORTED_PER_CHECK = 20
_WARN_PCT = 0.10  # rounding-noise budget
_ERROR_PCT = 1.0  # beyond this is not explainable by rounding - a real bug


class CompositeScoreReconciliationChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_composite_score_reconciliation(cur)
        return self.results

    def check_composite_score_reconciliation(self, cur: Any) -> None:
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (symbol)
                    symbol, date, quality_score, growth_score, value_score, risk_score,
                    momentum_score, composite_score
                FROM stock_scores
                WHERE composite_score IS NOT NULL
                ORDER BY symbol, date DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                pillar_scores = {
                    "quality": row["quality_score"],
                    "growth": row["growth_score"],
                    "value": row["value_score"],
                    "risk": row["risk_score"],
                    "momentum": row["momentum_score"],
                }
                risk_score = float(row["risk_score"]) if row["risk_score"] is not None else None
                weights = _value_risk_adjusted_weights(risk_score)
                recomputed = sum(
                    float(score) * weights[pillar] for pillar, score in pillar_scores.items() if score is not None
                )
                recomputed = round(max(0.0, min(100.0, recomputed)), 2)
                stored = float(row["composite_score"])
                divergence = abs(recomputed - stored)
                if divergence > _WARN_PCT:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "date": str(row["date"]),
                            "stored_composite_score": stored,
                            "recomputed_composite_score": recomputed,
                            "divergence": round(divergence, 4),
                            **{f"{p}_score": (float(s) if s is not None else None) for p, s in pillar_scores.items()},
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["divergence"], reverse=True)
                severity = ERROR if flagged[0]["divergence"] > _ERROR_PCT else WARN
                self.log(
                    "composite_score_reconciliation",
                    severity,
                    "stock_scores",
                    f"{len(flagged)} symbol(s) have a composite_score that doesn't reconcile to "
                    f"its own pillar inputs via BASE_PILLAR_WEIGHTS/_value_risk_adjusted_weights "
                    f"beyond a {_WARN_PCT}-point rounding budget (max divergence "
                    f"{flagged[0]['divergence']:.4f})",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
            else:
                # Always log even when clean (FIXED 2026-09-10, see pillar_score_reconciliation.py's
                # identical fix for the full rationale): a silent return on a clean pass can never
                # supersede/resolve an earlier flagged finding still marked 'open'.
                self.log(
                    "composite_score_reconciliation",
                    INFO,
                    "stock_scores",
                    "composite_score reconciles cleanly to its own pillar inputs",
                )
        except Exception as e:
            logger.error(
                f"[CompositeScoreReconciliationChecker] composite_score_reconciliation failed: {e}", exc_info=True
            )
            self.log(
                "composite_score_reconciliation",
                ERROR,
                "stock_scores",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )
