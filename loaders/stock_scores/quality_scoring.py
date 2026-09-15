"""QualityScoringMixin, extracted from load_stock_scores.py (2026-09-05, file-size-ratchet
bloaters-decomposition split). Moved verbatim - no behavior change.

Mixed into StockScoresLoader alongside the other stock_scores/*.py pillar mixins - every
`self.` reference here resolves normally through the instance regardless of which mixin file
defines it.
"""

import logging
from typing import TYPE_CHECKING, Any

from loaders.stock_scores.pillar_weights import BASE_PILLAR_WEIGHTS
from utils.loaders.unavailable_markers import marker_loader_failed, marker_not_applicable
from utils.type_conversion import safe_float

logger = logging.getLogger("loaders.load_stock_scores")


def _owner() -> Any:
    """Lazy reference to the owner module (loaders.load_stock_scores), resolved at call time -
    see loaders/stock_scores/value_metrics.py's identical `_owner()` for the full rationale.
    Copied verbatim, not re-derived, per this file's own "reuse the established pattern"
    mandate.
    """
    from loaders import load_stock_scores as _owner_mod

    return _owner_mod


class QualityScoringMixin:
    """See module docstring.

    `_quality_cache` is set on the instance by `_prepare_batch_context` (defined on
    StockScoresLoader itself, not any mixin) - declared type-checking-only below so mypy can
    see it without a real circular import.
    """

    if TYPE_CHECKING:
        _quality_cache: dict[str, tuple[Any, ...]]

    def _get_quality_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch quality metrics for symbol including Phase 3 expansion metrics.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 24 columns (10 base + 14 Phase 3 expansion)
        - Schema mismatch (len(row) < 24) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_quality_metrics_found"

        CRITICAL FIX 2026-07-23 (Session 359): Now fetches all Phase 3 expansion fields
        (gross_margin, ebitda_margin, roic_pct, fcf_to_net_income, ocf_to_net_income, payout_ratio,
        free_cash_flow, operating_cash_flow, total_debt, total_cash, cash_per_share, ebitda,
        earnings_growth_yoy, revenue_growth_yoy, interest_coverage). CORRECTED 2026-08-26:
        `_enhance_quality_score()` this comment referenced no longer exists - it was replaced
        entirely by `_score_quality`'s current weighted composite (see that method's own
        docstring for the current formula). Of this list, payout_ratio and interest_coverage
        are real weighted inputs in that composite today; roic_pct/fcf_to_net_income and the
        rest were tested and excluded (no independent signal) or are fetched for reference/
        display only - not all of them feed quality_score.

        MINIMUM DATA REQUIREMENT: Row must have exactly 25 columns. Missing columns causes immediate
        fail-fast ValueError to prevent silent data corruption.
        """
        row = self._quality_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 25 columns before accessing indices
            # (10 original + 14 Phase 3 expansion + 1 interest_coverage + 1 data_unavailable flag = 26 total, minus symbol = 25)
            if len(row) < 25:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: quality_metrics row has {len(row)} columns, expected 25. "
                    f"Schema mismatch detected - Phase 3 or interest_coverage fields missing. Failing fast."
                )
            data_unavailable = row[9]
            quality_score = safe_float(row[8], f"{symbol}.quality_score")
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in quality_metrics "
                    f"(likely REIT or security with missing SEC filings)"
                )
                return marker_not_applicable(symbol, "quality_metrics")
            # Row exists and data is available - return all fields including Phase 3 expansion
            return {
                "roe": safe_float(row[0], f"{symbol}.roe"),
                "roa": safe_float(row[1], f"{symbol}.roa"),
                "operating_margin": safe_float(row[2], f"{symbol}.operating_margin"),
                "net_margin": safe_float(row[3], f"{symbol}.net_margin"),
                "debt_to_equity": safe_float(row[4], f"{symbol}.debt_to_equity"),
                "current_ratio": safe_float(row[5], f"{symbol}.current_ratio"),
                "quick_ratio": safe_float(row[6], f"{symbol}.quick_ratio"),
                "debt_to_assets": safe_float(row[7], f"{symbol}.debt_to_assets", allow_none=True),
                "quality_score": quality_score,  # Pre-computed by load_value_quality_growth_metrics.py
                # Phase 3 expansion metrics (Session 358+)
                "gross_margin": safe_float(row[10], f"{symbol}.gross_margin", allow_none=True),
                "ebitda_margin": safe_float(row[11], f"{symbol}.ebitda_margin", allow_none=True),
                "roic_pct": safe_float(row[12], f"{symbol}.roic_pct", allow_none=True),
                "fcf_to_net_income": safe_float(row[13], f"{symbol}.fcf_to_net_income", allow_none=True),
                "ocf_to_net_income": safe_float(row[14], f"{symbol}.ocf_to_net_income", allow_none=True),
                "payout_ratio": safe_float(row[15], f"{symbol}.payout_ratio", allow_none=True),
                "free_cash_flow": safe_float(row[16], f"{symbol}.free_cash_flow", allow_none=True),
                "operating_cash_flow": safe_float(row[17], f"{symbol}.operating_cash_flow", allow_none=True),
                "total_debt": safe_float(row[18], f"{symbol}.total_debt", allow_none=True),
                "total_cash": safe_float(row[19], f"{symbol}.total_cash", allow_none=True),
                "cash_per_share": safe_float(row[20], f"{symbol}.cash_per_share", allow_none=True),
                "ebitda": safe_float(row[21], f"{symbol}.ebitda", allow_none=True),
                "earnings_growth_yoy": safe_float(row[22], f"{symbol}.earnings_growth_yoy", allow_none=True),
                "revenue_growth_yoy": safe_float(row[23], f"{symbol}.revenue_growth_yoy", allow_none=True),
                "interest_coverage": safe_float(row[24], f"{symbol}.interest_coverage", allow_none=True),
            }
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No quality metrics available for {symbol} - score completeness will be reduced"
        )
        return marker_loader_failed(symbol, "no_quality_metrics", "Quality metrics table missing data")

    def _score_quality(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score quality metrics on 0-100 scale.

        CRITICAL: Uses only pre-computed quality_score (official model consensus). No fallback
        computation - if pre-computed score missing, returns explicit data_unavailable marker.
        For financial accuracy, missing scores are better than fabricated heuristics.

        REBUILT 2026-08-26, EXTENDED 2026-08-27 (Quality pillar exhaustive-input review,
        user-directed - supersedes this docstring's earlier "9-weighted-component cluster
        blend" description, which described the c568eccfe state, not the current one). The
        upstream quality_score (loaders/helpers/vqg_quality_score.py) was an 8-weighted-
        component blend as of 2026-08-27: ROA 18%, ROCE 18% (replaced ROIC - fixed ROIC's
        cash-netting coverage gap), Debt-to-Equity 18% (replaced Debt-to-Assets - tested
        stronger, t=3.12 vs 2.18), FCF Margin 15% (replaced Accruals Ratio - independent
        signal, corr=0.13), ROE 11%, Margin Volatility (3Y)/Asset Turnover/Gross Profitability
        ~7% each. STALE AS OF 2026-09-15 (per-docstring drift this repo's own standing rule
        says to never trust without checking live code): ROCE and Asset Turnover were REMOVED
        from quality_components entirely that day (two-layer validation policy - no real
        institutional Quality definition scores them; raw roce_pct/asset_turnover still
        computed/persisted for other consumers, just not scored). Live is now a flat 1/6
        (~16.7%) equal weight across ROE/ROA/FCF Margin/Debt-to-Equity/Margin Volatility/Gross
        Profitability - check `vqg_quality_score.py`'s own `quality_components` list for the
        current authoritative weights rather than trusting this paragraph's numbers going
        forward. Renormalized over whichever are available for a given symbol, with a
        40-point minimum-available-weight floor (below that, quality_score is None rather than
        a thin-sample extrapolation - see vqg_quality_score.py's quality_components comment).
        Weights are set from both full-sample t-stat magnitude AND a half-split time-stability
        check, not raw t-stat alone.

        Interest Coverage/Payout Ratio REMOVED 2026-08-27: both were live at 5% each on
        nothing but legacy assumption - properly isolated FM re-testing (own dropna scope, not
        bundled with unrelated candidates) found neither ever approached significance
        (interest_coverage t=0.63/-0.12/0.87, payout_ratio t=0.53/0.68/0.06, full/1st-half/
        2nd-half). Gross Profitability (Novy-Marx 2013) was originally dropped the same day for
        the same reason (t=1.02) but that number came from a JOINT dropna across 7 unrelated
        candidate columns at once - isolated, it recovers to t=3.25/3.93/1.11, a real signal
        the biased test was hiding, the same failure mode later found to have also hidden
        Margin Volatility's signal and distorted Growth's eps/revenue 1y weights. Current Ratio
        was tested and excluded (no cross-sectional signal despite being a standard
        quality-investing checklist item) - that rejection used isolated methodology from the
        start and was re-confirmed, not reversed.

        Operating Margin Trend/Net Margin Trend/ROE Trend: relocated here from Growth
        2026-08-27 (per Piotroski/QMJ improvement-in-profitability placement), then REMOVED
        from scoring again the same day (user directive, live-observed "No data" on the
        StockDetail page). Unlike the Interest Coverage/Payout Ratio/Gross Profitability
        re-checks above, isolated re-testing did NOT recover a signal for any of these 3
        (t=0.55/0.08/-0.01 full-sample) - genuinely dead, not a joint-dropna casualty. Still
        computed/persisted (quality_metrics table), not scored. See
        load_value_quality_growth_metrics.py's quality_components comment for the fuller
        removal note on all of the above.

        Altman Z''-Score ADDED then REMOVED same day (2026-08-26, user directive) - not on new
        negative evidence, but a methodological objection: the literature frames Z''-Score as a
        discrete distress-triage classifier ("quick check of economic health; if it flags a
        problem, do more detailed analysis"), not a continuously-scaled input meant to be
        averaged into a magnitude-weighted composite - independently reinforcing what the data
        already flagged as this component's weakest point (its t=3.49 came from only 41 months
        and decayed hard within that short window, t=4.40->1.39 half-split). Removed from
        scoring first, then removed entirely (computation, persistence, API, frontend) on a
        2026-08-29 user directive that the raw value wasn't worth keeping for reference alone;
        where a distress-flag use belongs (if anywhere) is deliberately left open for later, not
        decided today.

        This REPLACES the previous "_enhance_quality_score" ±10-point bump layer entirely -
        every signal that layer used to bump on is now either a real weighted input in the
        base formula above, superseded by a literature-grounded replacement, or dropped as
        redundant. Splitting one quality signal across two differently-weighted functions in
        two different files was real architectural debt (user-flagged 2026-08-26) independent
        of the literature findings - collapsing to one function fixes both at once.
        _score_financial_stability/_score_dte removed as dead code (no other callers).
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Quality metrics unavailable for {symbol}")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_quality_metrics_data"}

        # CRITICAL: Require pre-computed quality_score. Do NOT fall back to dynamic computation -
        # that creates fabricated scores from heuristics. Missing quality_score indicates an
        # upstream issue (Phase 3 didn't run or metrics incomplete).
        if metrics.get("quality_score") is not None:
            quality_score_value = safe_float(metrics["quality_score"], f"{symbol}.quality_score")
            if quality_score_value is not None:
                logger.debug(f"[STOCK_SCORES] Using pre-computed quality_score for {symbol}: {quality_score_value}")
                return quality_score_value

        # FAIL-FAST: No pre-computed score and no fallback. This is explicit data unavailability.
        logger.warning(
            f"[STOCK_SCORES] Quality score unavailable for {symbol}. "
            f"Pre-computed quality_score missing - Phase 3 may not have completed or metrics incomplete. "
            f"Returning data_unavailable marker instead of fabricated heuristic score."
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "quality_score_unavailable"}

    def update_quality_from_source(self) -> None:
        """Batch pass: re-sync stock_scores.quality_score from quality_metrics.quality_score as
        it currently stands in the DB, and recompute composite_score/data_completeness/
        data_unavailable to match. ADDED 2026-09-15 (/goal session, live-caught bug:
        pillar_score_reconciliation DataPatrol check found 1,369 symbols - including NVDA,
        MSFT, WMT, XOM, V, PG, NFLX - with stock_scores.quality_score diverging from
        quality_metrics.quality_score by up to 26+ points, quarantining them out of the
        leaderboard entirely).

        EXTENDED 2026-09-15 (same session, quality liquidity-floor withhold fix - see
        loaders/helpers/vqg_quality_batch.py's `_withhold_quality_below_floor()` docstring for
        the full evidence trail): now ALSO propagates qm.quality_score transitioning to NULL
        (a withhold), not just non-NULL corrections - the original WHERE clause required
        `qm.quality_score IS NOT NULL`, which would silently DROP a withhold instead of syncing
        it, leaving stock_scores.quality_score permanently stuck on the stale pre-withhold
        value. This is a genuine re-sync-from-source in both directions now: whatever
        quality_metrics.quality_score currently holds (a real score OR None) is what
        stock_scores.quality_score is corrected to.

        ROOT CAUSE: unlike Risk/Value/Growth/Momentum (each of which has its own post_run()
        batch-correction pass below that re-reads its source table fresh), Quality was the one
        pillar computed ONLY from `self._quality_cache` - a single snapshot of the whole
        quality_metrics table taken once in `_prepare_batch_context()` before the main
        per-symbol loop runs (see load_stock_scores.py:435-443). `_score_quality` itself is a
        pure passthrough of quality_metrics.quality_score (no independent computation - "Uses
        only pre-computed quality_score... No fallback computation", see this file's own
        `_score_quality` docstring), so any staleness is entirely a cache-vs-live-table gap: if
        quality_metrics gets updated by anything else (a concurrent loader run, another
        session) while this run is in flight, stock_scores permanently carries the stale
        snapshot value with nothing to correct it afterward - the exact gap this pass closes,
        mirroring the self-healing pattern every sibling pillar already has.

        Runs FIRST in post_run() (before Risk/Value/Growth/Momentum) so their own composite
        recomputes see the corrected quality_score, not the stale cached one.

        Raises on failure, same as every other post_run() batch pass.
        """
        try:
            with _owner().DatabaseContext("write") as cur:
                cur.execute(
                    """
                    SELECT ss.symbol, ss.quality_score, ss.composite_score, ss.growth_score,
                           ss.value_score, ss.risk_score, ss.momentum_score,
                           ss.data_completeness, ss.data_unavailable, qm.quality_score
                    FROM stock_scores ss
                    JOIN quality_metrics qm ON qm.symbol = ss.symbol
                    WHERE ss.quality_score IS NOT NULL
                      AND COALESCE(qm.data_unavailable, false) = false
                    """
                )
                rows = cur.fetchall()

            if not rows:
                logger.warning(
                    "[STOCK_SCORES] update_quality_from_source: no eligible rows found - skipping, nothing to correct."
                )
                return

            min_completeness_threshold = getattr(self, "_min_completeness_threshold", 70.0)

            updates: list[tuple[str, float | None, float, float, bool]] = []
            for row in rows:
                (
                    symbol,
                    quality_score_old,
                    composite_score_old,
                    growth_score,
                    value_score,
                    risk_score,
                    momentum_score,
                    data_completeness_old,
                    data_unavailable_old,
                    quality_score_new,
                ) = row
                quality_score_new = float(quality_score_new) if quality_score_new is not None else None
                data_completeness_old = float(data_completeness_old) if data_completeness_old is not None else None
                data_unavailable_old = bool(data_unavailable_old) if data_unavailable_old is not None else False

                weights = BASE_PILLAR_WEIGHTS
                composite_val = 0.0
                for pillar_name, pillar_score in (
                    ("quality", quality_score_new),
                    ("growth", growth_score),
                    ("value", value_score),
                    ("risk", risk_score),
                    ("momentum", momentum_score),
                ):
                    if pillar_score is not None:
                        composite_val += float(pillar_score) * weights[pillar_name]
                composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)

                all_scores_new: dict[str, float | None] = {
                    "quality": quality_score_new,
                    "growth": float(growth_score) if growth_score is not None else None,
                    "value": float(value_score) if value_score is not None else None,
                    "risk": float(risk_score) if risk_score is not None else None,
                    "momentum": float(momentum_score) if momentum_score is not None else None,
                }
                available_weight = sum(
                    BASE_PILLAR_WEIGHTS[pillar] for pillar, score in all_scores_new.items() if score is not None
                )
                data_completeness_new = min(99.99, round(available_weight * 100, 2))
                data_unavailable_new = data_completeness_new < min_completeness_threshold

                quality_score_old_f = float(quality_score_old) if quality_score_old is not None else None
                if (
                    quality_score_new != quality_score_old_f
                    or composite_score_new != float(composite_score_old)
                    or data_completeness_new != data_completeness_old
                    or data_unavailable_new != data_unavailable_old
                ):
                    updates.append(
                        (
                            symbol,
                            quality_score_new,
                            composite_score_new,
                            data_completeness_new,
                            data_unavailable_new,
                        )
                    )

            if not updates:
                logger.info(
                    "[STOCK_SCORES] update_quality_from_source: no symbol's quality_score/"
                    "composite_score changed (expected once quality_metrics and stock_scores are back in sync)."
                )
                return

            with _owner().DatabaseContext("write") as cur:
                # ::numeric/::boolean casts on the VALUES columns (added alongside the
                # liquidity-floor withhold fix, 2026-09-15): quality_score can now be NULL in
                # the same batch as real floats (a withhold propagating from
                # _withhold_quality_below_floor()) - the identical mixed-None/float
                # wrong-inferred-column-type psycopg2 gotcha already hit and fixed for
                # momentum_score (see momentum_scoring.py's update_momentum_sector_relative_
                # mom_12_1() UPDATE, which already casts for the same reason).
                _owner().execute_values(
                    cur,
                    """
                    UPDATE stock_scores AS ss
                    SET quality_score = v.quality_score::numeric,
                        composite_score = v.composite_score::numeric,
                        data_completeness = v.data_completeness::numeric,
                        data_unavailable = v.data_unavailable::boolean,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (VALUES %s) AS v(symbol, quality_score, composite_score,
                                           data_completeness, data_unavailable)
                    WHERE ss.symbol = v.symbol
                    """,
                    updates,
                    template="(%s, %s, %s, %s, %s)",
                )
            logger.info(
                f"[STOCK_SCORES] Quality re-sync-from-source pass corrected "
                f"{len(updates)}/{len(rows)} symbols' quality_score/composite_score (post_run completed)"
            )
        except Exception as e:
            error_msg = f"Quality re-sync-from-source batch update failed: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
