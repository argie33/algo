"""QualityBatchMixin: _margin_curve/_weighted_avg/update_quality_sector_neutral_scores,
extracted from load_value_quality_growth_metrics.py (2026-09-08, file-size-ratchet compliance -
the sector-neutral-zscore rewrite pushed that already-past-ceiling file back over its baseline).
Moved verbatim, no behavior change.

_margin_curve/_weighted_avg are static helpers used both by this file's own
update_quality_sector_neutral_scores() and by vqg_quality.py's Pass-1 curve-based scoring
(`self._margin_curve`/`self._weighted_avg` there resolve to these via the same mixin diamond -
see vqg_quality.py's own module docstring for why that's harmless) - kept together here since
update_quality_sector_neutral_scores() is `_margin_curve`'s other real caller.

Uses the same `_owner()` lazy-import indirection vqg_quality.py already established, for the
identical reason: dozens of existing unit tests monkeypatch
``loaders.load_value_quality_growth_metrics.DatabaseContext``/``execute_values`` directly, which
a module-level import here could never reach, and importing the owner module eagerly at this
module's top level would risk the same mid-import circular-import crash vqg_quality.py's
docstring documents.
"""

import itertools
import logging
from typing import TYPE_CHECKING, Any

from loaders.helpers.factor_normalization import sector_neutral_zscore, zscore_to_percentile_scale


def _owner() -> Any:
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


logger = logging.getLogger("loaders.load_value_quality_growth_metrics")


class QualityBatchMixin:
    """See module docstring."""

    if TYPE_CHECKING:

        def _get_symbol_sector(self, symbol: str) -> str | None: ...

    @staticmethod
    def _margin_curve(value: float, breakpoints: list[tuple[float, float]]) -> float:
        """breakpoints: [(x0,y0), (x1,y1), ...] increasing x; value<x0 -> 0-ramp to y0,
        value>=last x -> last y. Piecewise-linear between points.

        Used by `_compute_quality_metrics`'s PROVISIONAL ROE/ROA/gross_profitability/roce_pct/
        fcf_margin/asset_turnover/margin_volatility score curves (Pass 1) - the final,
        authoritative quality_score comes from `update_quality_sector_neutral_scores()`'s
        sector-neutral z-scoring of the raw ratios, not this curve.
        """
        if value < 0:
            return 0.0
        if value < breakpoints[0][0]:
            x1, y1 = breakpoints[0]
            return (value / x1) * y1 if x1 > 0 else y1
        for (x0, y0), (x1, y1) in itertools.pairwise(breakpoints):
            if value < x1:
                return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
        return breakpoints[-1][1]

    @staticmethod
    def _weighted_avg(components: list[tuple[float | None, float]], min_weight_pct: float = 0.0) -> float | None:
        """components: [(score_or_None, weight), ...]. Renormalizes over whichever
        components are actually available, same "1/n over available" spirit as the old
        equal-weighted average, just weighted instead of equal. Returns None if the
        available weight doesn't clear min_weight_pct - renormalizing a 1-2 component
        sample up to a full 0-100 score is a thin-sample extrapolation, not an honest
        partial score (see quality_score's own call site for the live-verified case)."""
        available = [(v, w) for v, w in components if v is not None]
        total_weight = sum(w for _, w in available)
        if not available or total_weight <= 0 or total_weight < min_weight_pct:
            return None
        return sum(v * w for v, w in available) / total_weight

    def update_quality_sector_neutral_scores(self) -> None:
        """Batch pass: FULLY RECOMPUTE quality_score from scratch off the raw stored ratio
        columns (not patched relative to whatever quality_score currently holds), for every
        scored symbol in every sector - mirrors `update_rs_percentiles()`'s pure-overwrite
        pattern, NOT `update_value_multiples_percentiles()`'s additive-delta one.

        REWRITE 2026-09-07 ("best and brightest" scoring-methodology directive): published
        multi-factor methodology (MSCI Barra USE4/Factor Indexes, AQR Quality Minus Junk,
        Fama-French profitability construction) converges on ONE transform - winsorize, then
        z-score, computed within each symbol's own GICS sector as the peer group - for every
        raw ratio, not hand-tuned absolute curves whose SHAPE varies by industry/sector. This
        supersedes the prior scope of this method (ROE/ROCE percentile-ranked universe-wide,
        Financial Services/Real Estate/Utilities excluded entirely, the other 6 components
        left on their Pass-1 industry-curve scores): all 8 Quality sub-metrics, all sectors,
        via `sector_neutral_zscore()`/`zscore_to_percentile_scale()`
        (loaders/helpers/factor_normalization.py). This is now the sole authoritative source
        of quality_score - `_compute_quality_metrics`'s own curve-based composite
        (vqg_quality.py) is Pass-1 PROVISIONAL scaffolding this method always overwrites.

        MUST be a pure function of the raw stored ratio columns, never reading quality_score
        itself as an input: an earlier additive-delta design read/wrote the same mutable
        column every run, so the same delta re-applied on top of an already-corrected value
        each pipeline cycle with no convergence except the 0/100 clamp - over time this
        pinned ~30% of the universe at exactly 100.00.

        "Lower is better" metrics (debt_to_equity, margin_volatility) are z-scored on their
        NEGATED raw value, so a higher z-score means better quality for every component alike.

        Every non-negative-domain metric (roe/roa/roce/fcf_margin/asset_turnover/
        gross_profitability, plus debt_to_equity/margin_volatility after negation) is
        z-scored only over its non-negative population, with negative-raw-value symbols
        explicitly floored to 0.0 (matching Pass-1 `_margin_curve`'s own
        `if value < 0: return 0.0`) - a plain z-score doesn't floor at the bottom for a
        non-worst performer, which otherwise systematically over-scores unprofitable
        companies or (for debt_to_equity) a real negative-book-equity distress case.

        Sign-flip distress guard (live-confirmed 2026-09-07, 274 universe symbols, e.g. ROC
        roe=915.88%/roa=-38.43%): a negative-ROA (loss-making) company can only show a
        POSITIVE ROE when shareholders_equity is ALSO negative - a double-negative sign
        flip, not genuine profitability. The ROE component is omitted entirely if roa is
        missing, and floored to 0.0 (not z-scored) if roe<0 OR roa<0 - unchanged from the
        prior ROE/ROCE-only version of this method.

        Raises on failure, same as every other post_run() batch pass - an inconsistent
        quality_score is a live-trading-relevant correctness issue.
        """
        try:
            with _owner().DatabaseContext("write") as cur:
                cur.execute("""
                    SELECT qm.symbol, cp.sector, qm.roe, qm.roa, qm.roce_pct, qm.fcf_margin,
                           qm.debt_to_equity, qm.margin_volatility, qm.asset_turnover, qm.gross_profitability,
                           qm.quality_score
                    FROM quality_metrics qm
                    LEFT JOIN company_profile cp ON cp.symbol = qm.symbol
                    WHERE qm.quality_score IS NOT NULL
                      AND COALESCE(qm.data_unavailable, false) = false
                """)
                rows = cur.fetchall()

            if not rows:
                logger.warning(
                    "[QUALITY_METRICS] update_quality_sector_neutral_scores: no eligible rows found - skipping."
                )
                return

            # Sector peer group for the z-score - a symbol with no company_profile.sector row
            # simply has no entry here, which sector_neutral_zscore() pools into its residual
            # group rather than dropping (see that function's own docstring).
            sectors: dict[str, str] = {row[0]: row[1] for row in rows if row[1]}

            def _nonneg_raw(idx: int) -> dict[str, float]:
                return {row[0]: float(row[idx]) for row in rows if row[idx] is not None and float(row[idx]) >= 0.0}

            def _negated_nonneg_raw(idx: int) -> dict[str, float]:
                # "lower is better" metrics: negate before z-scoring so a higher z always
                # means better quality, matching every other component's direction.
                return {row[0]: -float(row[idx]) for row in rows if row[idx] is not None and float(row[idx]) >= 0.0}

            # roe additionally requires roa present and non-negative - the sign-flip guard
            # above; a roe<0 or roa<0 symbol is excluded from the z-score population and
            # floored to 0.0 directly in the per-symbol loop below, same as every other metric.
            roe_raw = {
                row[0]: float(row[2])
                for row in rows
                if row[2] is not None and row[3] is not None and float(row[2]) >= 0.0 and float(row[3]) >= 0.0
            }
            roa_raw = _nonneg_raw(3)
            roce_raw = _nonneg_raw(4)
            fcf_margin_raw = _nonneg_raw(5)
            d2e_raw = _negated_nonneg_raw(6)
            margin_vol_raw = _negated_nonneg_raw(7)
            asset_turnover_raw = _nonneg_raw(8)
            gross_prof_raw = _nonneg_raw(9)

            roe_pct = zscore_to_percentile_scale(sector_neutral_zscore(roe_raw, sectors))
            roa_pct = zscore_to_percentile_scale(sector_neutral_zscore(roa_raw, sectors))
            roce_pct = zscore_to_percentile_scale(sector_neutral_zscore(roce_raw, sectors))
            fcf_margin_pct = zscore_to_percentile_scale(sector_neutral_zscore(fcf_margin_raw, sectors))
            d2e_pct = zscore_to_percentile_scale(sector_neutral_zscore(d2e_raw, sectors))
            margin_vol_pct = zscore_to_percentile_scale(sector_neutral_zscore(margin_vol_raw, sectors))
            asset_turnover_pct = zscore_to_percentile_scale(sector_neutral_zscore(asset_turnover_raw, sectors))
            gross_prof_pct = zscore_to_percentile_scale(sector_neutral_zscore(gross_prof_raw, sectors))
            logger.info(
                f"[QUALITY_METRICS] sector-neutral z-score universe: roe={len(roe_pct)} roa={len(roa_pct)} "
                f"roce={len(roce_pct)} fcf_margin={len(fcf_margin_pct)} debt_to_equity={len(d2e_pct)} "
                f"margin_volatility={len(margin_vol_pct)} asset_turnover={len(asset_turnover_pct)} "
                f"gross_profitability={len(gross_prof_pct)}"
            )

            updates: list[tuple[str, float]] = []
            for row in rows:
                symbol, quality_score_old = row[0], float(row[10])
                roe, roa, roce_pct_val, fcf_margin, d2e, margin_vol, asset_turnover, gross_prof = row[2:10]

                components: list[tuple[float, float]] = []

                # A negative roe is floored to 0.0 outright, regardless of whether roa is
                # available - the roa-presence requirement below exists only to catch the
                # sign-flip case (roe spuriously POSITIVE while roa is negative), which is
                # moot once roe is already negative. Requiring roa unconditionally previously
                # omitted the component entirely (not floored) for a negative-roe symbol with
                # no roa on file, silently excluding a genuinely bad performer from
                # quality_score instead of scoring it 0 - fixed 2026-09-08.
                if roe is not None and float(roe) < 0.0:
                    components.append((0.0, 11.0))
                elif roe is not None and roa is not None:  # roa<0 = sign-flip distress artifact
                    roe_component = 0.0 if float(roa) < 0.0 else roe_pct[symbol]
                    components.append((roe_component, 11.0))
                if roa is not None:
                    roa_component = 0.0 if float(roa) < 0.0 else roa_pct[symbol]
                    components.append((roa_component, 18.0))
                if roce_pct_val is not None:
                    roce_component = 0.0 if float(roce_pct_val) < 0.0 else roce_pct[symbol]
                    components.append((roce_component, 18.0))
                if fcf_margin is not None:
                    fcf_component = 0.0 if float(fcf_margin) < 0.0 else fcf_margin_pct[symbol]
                    components.append((fcf_component, 15.0))
                if d2e is not None:
                    # Negative D/E (negative book equity) is real distress, not a scale
                    # issue - floored to 0.0 the same as every other metric's negative case,
                    # never inverted into a spuriously high score.
                    d2e_component = 0.0 if float(d2e) < 0.0 else d2e_pct[symbol]
                    components.append((d2e_component, 18.0))
                if margin_vol is not None:
                    # Volatility can't be genuinely negative - no floor case, just z-scored.
                    components.append((margin_vol_pct[symbol], 7.0))
                if asset_turnover is not None:
                    at_component = 0.0 if float(asset_turnover) < 0.0 else asset_turnover_pct[symbol]
                    components.append((at_component, 7.0))
                if gross_prof is not None:
                    gp_component = 0.0 if float(gross_prof) < 0.0 else gross_prof_pct[symbol]
                    components.append((gp_component, 7.0))

                total_weight = sum(w for _, w in components)
                if total_weight <= 0:
                    continue  # defensive only - can't happen if quality_score is real

                quality_score_new = round(max(0.0, min(100.0, sum(v * w for v, w in components) / total_weight)), 2)
                if quality_score_new != quality_score_old:
                    updates.append((symbol, quality_score_new))

            if not updates:
                logger.info("[QUALITY_METRICS] sector-neutral z-score pass: no eligible symbols to update.")
                return

            with _owner().DatabaseContext("write") as cur:
                _owner().execute_values(
                    cur,
                    """
                    UPDATE quality_metrics AS qm
                    SET quality_score = v.quality_score,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (VALUES %s) AS v(symbol, quality_score)
                    WHERE qm.symbol = v.symbol
                    """,
                    updates,
                    template="(%s, %s)",
                )
            logger.info(
                f"[QUALITY_METRICS] sector-neutral z-score pass recomputed quality_score for "
                f"{len(updates)}/{len(rows)} symbols (post_run completed)"
            )
        except (_owner().psycopg2.DatabaseError, _owner().psycopg2.OperationalError) as e:
            error_msg = f"sector-neutral quality batch update failed - quality_metrics cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
