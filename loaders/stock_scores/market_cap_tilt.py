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

from loaders.stock_scores.pillar_weights import DEFAULT_MIN_INVESTABLE_MARKET_CAP
from utils.loaders.helpers import NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE

logger = logging.getLogger("loaders.load_stock_scores")

# MARKET_CAP_TILT_K: weight = market_cap * max(0.1, 1 + k * z_score). Independently converged
# on and verified this session (two independently-built measurements: 84%/76% top-25 overlap
# vs real LRGF+GSLC holdings at k=0.2, up from 68% at k=0.0/pure-cap - see
# [[overlap_bottom25_exclusion_baserate_caveat_20260915]] in memory for the honest caveat on
# the bottom-25 side of that same measurement: report lift over the ~75% null base rate, not
# the raw percentage, for that half).
MARKET_CAP_TILT_K = 0.2

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
        """Batch pass: compute market_cap * max(0.1, 1 + k*z) for composite_score and each of
        the 5 pillar scores, over the same eligible universe convention every sibling
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
                    WHERE vm.market_cap >= %s
                      AND ("""
                    + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                    + ")",
                    (getattr(self, "_min_investable_market_cap", None) or DEFAULT_MIN_INVESTABLE_MARKET_CAP,),
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
                    tilt = max(0.1, 1 + MARKET_CAP_TILT_K * z)
                    weights[symbol] = float(market_cap) * tilt
                tilted_by_column[score_col] = weights

            updates: list[tuple[Any, ...]] = []
            for row in rows:
                symbol = row[0]
                values_for_row = tuple(tilted_by_column[score_col].get(symbol) for score_col, _ in _TILT_COLUMNS)
                updates.append((symbol, *values_for_row))

            with _owner().DatabaseContext("write") as cur:
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
            logger.info(f"[STOCK_SCORES] Market-cap tilted weights computed for {len(updates)}/{len(rows)} symbols.")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"Market-cap tilted weight batch update failed: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
