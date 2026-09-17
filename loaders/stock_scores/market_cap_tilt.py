"""MarketCapTiltMixin: batch pass that computes and stores market-cap-tilted display weights
on stock_scores (migration 1294).

REPLACES request-time tilt computation duplicated across two API endpoints (lambda/api/routes/
algo_handlers/dashboard/scores.py's _apply_market_cap_tilt, merged 2026-09-15) and a near-third
copy drafted directly in webapp/frontend/src/pages/ScoresDashboard.jsx before being caught and
reverted the same session. Live-caught bug: the Python tilt only ever reached /api/algo/scores -
the actual page the user looks at calls a different endpoint (/api/scores/stockscores) that
never got it, so the dashboard kept showing raw-percentile micro/small-cap "leaders" with no
cap-weighting. See migrations/versions/1294_add_market_cap_tilted_weights_to_stock_scores.sql's
own header comment for the full "compute once, not per-consumer" rationale (mirrors how real
institutional multi-factor index providers - Goldman ActiveBeta, the tractable-to-replicate one
of the two funds checked this session - compute their factor-tilted construction once on a
schedule and publish it, not live-recompute a formula in every consuming surface).

NOT a change to composite_score/pillar scores themselves, which stay pure factor-merit and
continue driving live Phase 7/8 trading decisions unchanged - these are DISPLAY-only columns.

Mixed into StockScoresLoader alongside the other stock_scores/*.py pillar mixins - every
`self.` reference here resolves normally through the instance regardless of which mixin file
defines it.
"""

import logging
from typing import Any

import psycopg2

from loaders.stock_scores.pillar_weights import (
    DEFAULT_MIN_ADV_DOLLARS,
    DEFAULT_MIN_STOCK_PRICE,
    LIQUIDITY_FLOOR_JOIN_SQL,
)
from utils.loaders.helpers import NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE

logger = logging.getLogger("loaders.load_stock_scores")

# TILT_ZSCORE_WINSORIZE_BOUND / _tilt_score_from_zscore: REPLACES the fitted MARKET_CAP_TILT_K
# damping constant (k=0.2, reverse-engineered 2026-09-15 by trying values until the output
# matched ~84%/76% of two real ETFs' actual holdings - see git history for that superseded
# version) with MSCI's own real, published Tilt Index formula (user directive 2026-09-16:
# "get rid of all the extra shit beyond ... the industry guys"; a fitted constant tuned to
# match an outcome is exactly that "shit", however well it happened to score). Verified
# directly against MSCI Momentum Indexes Methodology, August 2021, section 2.2.2 (fetched and
# read this session, not recalled from memory):
#
#   Momentum Z-score winsorized at +/-3 (values above 3 capped to 3, below -3 capped to -3)
#   Momentum Score = 1 + Z              if Z > 0
#   Momentum Score = (1 - Z)^-1         if Z < 0
#   Tilt Weight = Momentum Score * Market-Cap-Weight-in-Parent-Index (then renormalized)
#
# Asymmetric on purpose (MSCI's own construction, not this repo's invention) - it keeps the
# multiplier strictly positive across the full winsorized range (0.25x at Z=-3 to 4x at Z=+3)
# with no separate floor constant needed, unlike the old max(0.1, ...) clamp that existed only
# to patch the old symmetric formula's ability to go negative below z=-4.5 (an artifact of the
# old formula, not something the real one needs). No fitted scaling constant anywhere - the
# z-score itself (after winsorization) IS the tilt strength, exactly as published. Renormalizing
# to 100% doesn't change relative ORDER (a uniform divisor across every row) - these columns are
# read only via ORDER BY, never as real portfolio weights, so renormalization is correctly
# omitted here, same simplification already applied to the pre-existing market_cap multiplication
# (also not divided by total universe market cap for the same reason).
TILT_ZSCORE_WINSORIZE_BOUND = 3.0


def _tilt_score_from_zscore(z: float) -> float:
    """MSCI's published Momentum Tilt Index Score formula (see module-level comment above),
    applied generically to every pillar's z-score here.

    CROSS-FACTOR REUSE - NOW EQUATION-LEVEL VERIFIED FOR A SECOND FACTOR (2026-09-16,
    factor-purity sweep follow-up): fetched MSCI's Quality Indexes Methodology, May 2022
    (msci.com/eqb/methodology/meth_docs/MSCI_Quality_Indexes_Methodology_May2022.pdf) directly
    this session. Section 2.2.3 gives the IDENTICAL piecewise formula already implemented here
    (Quality Score = 1+Z for Z>=0, (1-Z)^-1 for Z<0), and Appendix VI's sector-relative variant
    is winsorized at the same +/-3 bound. Appendix V ("Constructing MSCI Quality Tilt Index")
    states in plain text: "The MSCI Quality Tilt Index follows the same weighting scheme as the
    MSCI Quality Index" - the same "[Factor] Tilt Index reuses [Factor] Index's own Score-to-
    Weight construction" pattern already confirmed for Momentum, now confirmed equation-level
    (not just structural) for a second, independently-documented factor. Still not independently
    checked for Value/Volatility/Size/Dividend specifically, but two-for-two on the exact same
    formula/bound is strong evidence this is MSCI's genuinely shared Tilt Index construction,
    not something this repo invented and is calling "MSCI" without support."""
    z = max(-TILT_ZSCORE_WINSORIZE_BOUND, min(TILT_ZSCORE_WINSORIZE_BOUND, z))
    return 1 + z if z > 0 else 1 / (1 - z)


# The 6 (score_column, weight_column) pairs this pass computes - one per pillar plus
# composite, matching how real ActiveBeta-style construction tilts EACH factor sub-index
# independently by that factor's own z-score before combining (not just an overall tilt).
_TILT_COLUMNS = (
    ("composite_score", "composite_tilted_weight"),
    ("momentum_score", "momentum_tilted_weight"),
    ("quality_score", "quality_tilted_weight"),
    ("value_score", "value_tilted_weight"),
    ("growth_score", "growth_tilted_weight"),
    ("risk_score", "risk_tilted_weight"),
)


def _owner() -> Any:
    """Lazy reference to the owner module - same rationale/precedent as every sibling batch
    pass's own `_owner()` (see momentum_scoring.py's copy for the full docstring)."""
    import sys

    return sys.modules.get("loaders.load_stock_scores") or sys.modules["__main__"]


class MarketCapTiltMixin:
    def update_market_cap_tilted_weights(self) -> None:
        """Batch pass: compute market_cap * _tilt_score_from_zscore(z) (MSCI's real published
        Tilt Index piecewise formula - see this module's own top-of-file comment, replacing the
        old fitted `max(0.1, 1 + k*z)` damping constant 2026-09-16) for composite_score and each
        of the 5 pillar scores, over the same eligible universe convention every sibling
        sector-neutral pass already uses (investability floor, non-ETF, non-operating-company
        exclusion), and store the result in stock_scores' 6 *_tilted_weight columns (migration
        1294). Pure overwrite every run (same "restart-only, not incremental" pattern as
        update_momentum_sector_relative_mom_12_1/update_growth_sector_neutral_scores) - a
        symbol's tilted weight is a function of the CURRENT run's whole population (mean/stdev
        of that score), so it must be fully recomputed whenever any pillar's scores change, not
        patched.

        Rows with a NULL score for a given column, or missing/non-positive market_cap, get a
        NULL tilted weight for that column (never a fabricated fallback) - same "skip what's
        unavailable, never exclude the row" principle as every pillar in this codebase.

        MUST run LAST in post_run(), after every pillar's own batch pass has finalized its
        score (update_risk_absolute_zscore_scores/update_value_multiples_percentiles/
        update_growth_sector_neutral_scores/update_momentum_sector_relative_mom_12_1) and
        composite_score is fully settled - tilting off a provisional Pass-1 score would produce
        a stale weight the instant any later pass changes that pillar.

        DISPLAY-ONLY: these columns are never read by composite_score, pillar scoring, or any
        Phase 7/8 trading logic - only by the two dashboard-facing API endpoints, which this
        pass exists specifically so they no longer need their own duplicate copy of this
        formula (see this module's own docstring for the concurrency bug this closes).

        Raises on failure, same as every other post_run() batch pass - stale/missing tilted
        weights would leave the dashboard silently showing an old ranking with no indication
        anything is wrong.
        """
        try:
            with _owner().DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT ss.symbol, ss.composite_score, ss.momentum_score, ss.quality_score,
                           ss.value_score, ss.growth_score, ss.risk_score, vm.market_cap
                    FROM stock_scores ss
                    JOIN value_metrics vm ON vm.symbol = ss.symbol
                    JOIN stock_symbols su ON su.symbol = ss.symbol
                    LEFT JOIN company_info_sec cis ON cis.symbol = ss.symbol
                    """
                    + LIQUIDITY_FLOOR_JOIN_SQL
                    + """
                    WHERE liq_floor.latest_close >= %s
                      AND liq_floor.avg_dollar_volume_20d >= %s
                      AND ("""
                    + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                    + ")",
                    (
                        getattr(self, "_min_stock_price", None) or DEFAULT_MIN_STOCK_PRICE,
                        getattr(self, "_min_adv_dollars", None) or DEFAULT_MIN_ADV_DOLLARS,
                    ),
                )
                rows = cur.fetchall()

            if not rows:
                logger.warning("[STOCK_SCORES] update_market_cap_tilted_weights: no eligible rows found - skipping.")
                return

            # Column indices into each row, matching the SELECT above.
            col_idx = {
                "composite_score": 1,
                "momentum_score": 2,
                "quality_score": 3,
                "value_score": 4,
                "growth_score": 5,
                "risk_score": 6,
            }
            mcap_idx = 7

            tilted_by_column: dict[str, dict[str, float]] = {}
            for score_col, _weight_col in _TILT_COLUMNS:
                idx = col_idx[score_col]
                values = [float(row[idx]) for row in rows if row[idx] is not None]
                if len(values) < 2:
                    tilted_by_column[score_col] = {}
                    continue
                mean = sum(values) / len(values)
                variance = sum((v - mean) ** 2 for v in values) / len(values)
                stdev = variance**0.5
                if stdev <= 0:
                    tilted_by_column[score_col] = {}
                    continue
                weights: dict[str, float] = {}
                for row in rows:
                    symbol = row[0]
                    score = row[idx]
                    market_cap = row[mcap_idx]
                    if score is None or market_cap is None or float(market_cap) <= 0:
                        continue
                    z = (float(score) - mean) / stdev
                    tilt = _tilt_score_from_zscore(z)
                    weights[symbol] = float(market_cap) * tilt
                tilted_by_column[score_col] = weights

            updates: list[tuple[Any, ...]] = []
            for row in rows:
                symbol = row[0]
                values_for_row = tuple(tilted_by_column[score_col].get(symbol) for score_col, _ in _TILT_COLUMNS)
                updates.append((symbol, *values_for_row))

            eligible_symbols = [row[0] for row in rows]

            with _owner().DatabaseContext("write") as cur:
                # FIXED 2026-09-15 (goal: LRGF/GSLC top-25 side-by-side audit - live-caught via
                # the SKHY/SK hynix bad-market-cap fix just above in this same session): this
                # pass's own docstring promises "Pure overwrite every run" / "must be fully
                # recomputed", but the UPDATE below only ever touched symbols present in `rows`
                # (this run's eligible population) - a symbol that WAS eligible on a prior run
                # (bad market_cap slipped past the eligibility floor, or genuinely fell out of
                # the investable universe/non-operating-company exclusion since) but is NOT
                # eligible this run kept its stale *_tilted_weight values forever, since nothing
                # ever nulled them back out. Live-reproduced this exact gap: after fixing SKHY's
                # upstream market_cap to correctly go NULL (foreign_private_issuer_shares_
                # unavailable), SKHY dropped out of `rows` here as expected, but its already-
                # stored composite_tilted_weight ($1.005T, rank #13 in the live top-25) survived
                # this pass completely unchanged and kept appearing in the dashboard's top-25 -
                # the exact "slop" class this whole audit was asked to find. Null every
                # *_tilted_weight column for any symbol NOT in this run's eligible set (not just
                # the ones this run recomputed) before applying this run's real values, so a
                # symbol that drops out of eligibility for ANY reason (bad data, delisting,
                # newly-excluded as a non-operating company, etc.) can never keep serving a
                # previous run's number.
                cur.execute(
                    """
                    UPDATE stock_scores
                    SET composite_tilted_weight = NULL,
                        momentum_tilted_weight = NULL,
                        quality_tilted_weight = NULL,
                        value_tilted_weight = NULL,
                        growth_tilted_weight = NULL,
                        risk_tilted_weight = NULL
                    WHERE NOT (symbol = ANY(%s))
                      AND (composite_tilted_weight IS NOT NULL OR momentum_tilted_weight IS NOT NULL
                           OR quality_tilted_weight IS NOT NULL OR value_tilted_weight IS NOT NULL
                           OR growth_tilted_weight IS NOT NULL OR risk_tilted_weight IS NOT NULL)
                    """,
                    (eligible_symbols,),
                )
                stale_cleared = cur.rowcount
                _owner().execute_values(
                    cur,
                    """
                    UPDATE stock_scores AS ss
                    SET composite_tilted_weight = v.composite_tilted_weight,
                        momentum_tilted_weight = v.momentum_tilted_weight,
                        quality_tilted_weight = v.quality_tilted_weight,
                        value_tilted_weight = v.value_tilted_weight,
                        growth_tilted_weight = v.growth_tilted_weight,
                        risk_tilted_weight = v.risk_tilted_weight
                    FROM (VALUES %s) AS v(symbol, composite_tilted_weight, momentum_tilted_weight,
                                           quality_tilted_weight, value_tilted_weight,
                                           growth_tilted_weight, risk_tilted_weight)
                    WHERE ss.symbol = v.symbol
                    """,
                    updates,
                    template="(%s, %s, %s, %s, %s, %s, %s)",
                )
            logger.info(
                f"[STOCK_SCORES] Market-cap tilted weights computed for {len(updates)}/{len(rows)} symbols "
                f"({stale_cleared} stale out-of-population rows cleared)."
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"Market-cap tilted weight batch update failed: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
