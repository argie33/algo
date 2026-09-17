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

from loaders.helpers.factor_normalization import (
    sector_neutral_zscore,
    universe_wide_zscore,
    zscore_to_percentile_scale,
)
from loaders.helpers.vqg_quality_debt_fallback import DebtComponentsFallbackMixin
from loaders.helpers.vqg_shared import apply_mortgage_reit_sector_override
from loaders.stock_scores.pillar_weights import (
    DEFAULT_MIN_ADV_DOLLARS,
    DEFAULT_MIN_STOCK_PRICE,
    LIQUIDITY_FLOOR_JOIN_SQL,
)
from utils.loaders.helpers import NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE


def _owner() -> Any:
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


logger = logging.getLogger("loaders.load_value_quality_growth_metrics")


class QualityBatchMixin(DebtComponentsFallbackMixin):
    """See module docstring. Also carries DebtComponentsFallbackMixin so
    ValueQualityGrowthMetricsLoader picks up _fetch_total_debt_components_fallback via this
    already-inherited mixin, same diamond-inheritance precedent as _margin_curve/_weighted_avg
    above - avoids adding another base to load_value_quality_growth_metrics.py's own class
    statement (already past the file-size-ratchet hard ceiling, blocked from any growth)."""

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

    def _withhold_quality_below_floor(self) -> list[tuple[str, float | None]]:
        """Companion to update_quality_sector_neutral_scores(): finds the COMPLEMENT of that
        method's own correction population - symbols with a real (non-NULL, non-data_unavailable)
        quality_metrics.quality_score that are ineligible for the sector-neutral correction pass
        (below the liquidity floor, or excluded by NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE)
        - and withholds quality_score (NULL) instead of leaving Pass-1's stale, potentially-
        floored curve value in place indefinitely.

        LINEAGE (added 2026-09-15): same failure mode as the momentum-saturation bug fixed in
        loaders/stock_scores/momentum_scoring.py's `_withhold_momentum_below_floor()` (commit
        c1a3dd899), just manifesting at the BOTTOM of the scale instead of the top - update_
        quality_sector_neutral_scores()'s own docstring already documents "Sub-floor symbols
        simply aren't included in this pass and keep whatever Pass-1 already gave them", and
        Pass-1's `_margin_curve` floors negative-ROE/ROA (sign-flip distress) symbols to 0.0 -
        so a sub-floor symbol that happens to be loss-making stays pinned at quality_score=0.0
        forever instead of getting a proper cross-sectional score once/if it clears the floor.
        Live-confirmed 2026-09-15: 115 of the 179 symbols with quality_score<=1.0 in the live DB
        are below the liquidity floor.

        Only touches quality_metrics.quality_score - propagation to stock_scores.quality_score/
        composite_score happens in loaders/stock_scores/quality_scoring.py's
        update_quality_from_source(), which now also propagates a NULL-ing withhold (previously
        it required qm.quality_score IS NOT NULL, which would silently DROP this withdrawal
        instead of syncing it - see that method's own docstring for the fix).

        Returns (symbol, None) tuples in the same shape update_quality_sector_neutral_scores()'s
        own `updates` list uses, so the caller can extend one batch UPDATE with both.
        """
        with _owner().DatabaseContext("write") as cur:
            cur.execute(
                """
                SELECT qm.symbol
                FROM quality_metrics qm
                JOIN stock_scores ss ON ss.symbol = qm.symbol
                JOIN stock_symbols su ON su.symbol = qm.symbol
                LEFT JOIN company_info_sec cis ON cis.symbol = qm.symbol
                """
                + LIQUIDITY_FLOOR_JOIN_SQL
                + """
                WHERE qm.quality_score IS NOT NULL
                  AND COALESCE(qm.data_unavailable, false) = false
                  AND (
                        liq_floor.latest_close IS NULL
                        OR liq_floor.latest_close < %s
                        OR liq_floor.avg_dollar_volume_20d IS NULL
                        OR liq_floor.avg_dollar_volume_20d < %s
                        OR NOT ("""
                + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                + """)
                  )
                """,
                (
                    getattr(self, "_min_stock_price", None) or DEFAULT_MIN_STOCK_PRICE,
                    getattr(self, "_min_adv_dollars", None) or DEFAULT_MIN_ADV_DOLLARS,
                ),
            )
            rows = cur.fetchall()

        if not rows:
            # No symbols below the liquidity floor / excluded from the scoring population -
            # nothing to process, not a data-fetch failure.
            return []

        withheld: list[tuple[str, float | None]] = [(row[0], None) for row in rows]
        logger.info(
            f"[QUALITY_METRICS] withheld quality_score for {len(withheld)} symbols below the "
            f"liquidity floor / excluded from the scoring population (never reached by the "
            f"correction pass above) - see _withhold_quality_below_floor's docstring."
        )
        return withheld

    def update_quality_sector_neutral_scores(self) -> None:
        """Batch pass: FULLY RECOMPUTE quality_score from scratch off the raw stored ratio
        columns (not patched relative to whatever quality_score currently holds), for every
        scored symbol in every sector - mirrors `update_rs_percentiles()`'s pure-overwrite
        pattern, NOT `update_value_multiples_percentiles()`'s additive-delta one.

        REBUILT TO MSCI'S EXACT 3-VARIABLE QUALITY INDEX 2026-09-16 (factor-purity sweep,
        user: "we do what the industry does only" - SUPERSEDES the 8-metric AQR/MSCI blend
        this method used from 2026-09-07 through 2026-09-15, see git history for that version).
        Fetched and read MSCI's real, published Quality Indexes Methodology directly this
        session (msci.com/eqb/methodology/meth_docs/MSCI_Quality_Indexes_Methodology_
        May2022.pdf, Section 2.2 + Appendix I/II) - not recalled/paraphrased. MSCI's real
        3-step construction (identical shape to Value's own MSCI-formula rebuild the same
        session - see loaders/stock_scores/value_metrics.py's update_value_multiples_
        percentiles() for the sibling implementation):
          1. z-score EACH of the 3 fundamental variables (Return on Equity, Debt to Equity,
             Earnings Variability - see loaders/helpers/quality_variability.py for the 3rd)
             UNIVERSE-WIDE (within the whole eligible universe, "the MSCI Parent Index" - NOT
             per-sector - see universe_wide_zscore below). "Lower is better" variables
             (Debt to Equity, Earnings Variability) are negated before z-scoring so a higher
             z always means better quality, matching ROE's own direction.
          2. composite = equal-weighted average of the available variable z-scores (1/3 each,
             or 1/2 for the 2-of-3 substitution cases MSCI's Appendix II states - Cases 2/3).
             ROE IS MANDATORY (Appendix II Cases 1/4: missing ROE means no score at all, even
             if the other two are both present) - enforced explicitly, not just via the
             completeness floor below.
          3. SECTOR-relativize the COMPOSITE (not each variable individually, and only once)
             by standardizing it within each GICS sector (sector_neutral_zscore - MSCI's own
             separate "Sector Neutral Quality Index" variant, Appendix VI, which this repo's
             cross-sector-comparability goals already lean toward, same choice Value made),
             then winsorize the result at +/-3 - MSCI's own explicitly stated output bound.
        Final 0-100 conversion uses zscore_to_percentile_scale (the same normal-CDF transform
        this codebase already uses to bound every other z-score-based pillar/leg to [0,100]),
        not MSCI's own "Quality Score" piecewise transform (1+Z / (1-Z)^-1) - see Value's own
        rebuild docstring for why: that transform is a PORTFOLIO-WEIGHTING construction, not a
        rating scale, and stays reserved for loaders/stock_scores/market_cap_tilt.py's
        *_tilted_weight columns, its correct domain.

        DROPPED to match MSCI exactly: roa/fcf_margin/gross_profitability (AQR QMJ
        Profitability-leg additions, not part of MSCI's 3-variable index) and margin_volatility
        (this repo's own AQR-Safety-leg stand-in for Earnings Variability, a related-but-
        distinct metric - margin stability, not EPS-growth-rate stability). All 4 raw values
        stay computed/persisted/displayed - same "computed but unscored" convention as every
        other removed-from-scoring input elsewhere in this codebase (Value's ev_ebitda/
        ev_revenue/dividend_yield, etc.) - only their vote in quality_score is removed. The
        FS-bank/insurance/utility industry-split peer groups this method used to build for
        roe/roa/d2e's z-scoring are no longer needed: MSCI's real construction z-scores each
        variable universe-wide (step 1), not per-sector at all, so a finer sub-sector split at
        that stage has no analog in the real methodology - dropped along with the components
        that needed it, not carried forward as unused machinery.

        MUST be a pure function of the raw stored ratio columns, never reading quality_score
        itself as an input: an earlier additive-delta design read/wrote the same mutable
        column every run, so the same delta re-applied on top of an already-corrected value
        each pipeline cycle with no convergence except the 0/100 clamp - over time this
        pinned ~30% of the universe at exactly 100.00.

        Sign-flip distress guard (live-confirmed 2026-09-07, 274 universe symbols, e.g. ROC
        roe=915.88%/roa=-38.43%): a negative-ROA (loss-making) company can only show a
        POSITIVE ROE when shareholders_equity is ALSO negative - a double-negative sign
        flip, not genuine profitability. roa is READ here purely as this data-quality gate on
        ROE (not itself scored, per the DROPPED note above) - the ROE component is omitted
        entirely if roa is missing, and floored to the worst z-score (-3, MSCI's own
        winsorization bound, the natural "worst" sentinel - same convention Value's rebuild
        established) if roe<0 OR roa<0, unchanged reasoning from the prior version of this
        method.

        INVESTABILITY FLOOR ADDED 2026-09-13 (`vm.market_cap >= %s`, algo_config.min_market_
        cap_millions, same $300M threshold LiquidityChecks._check_market_cap() now enforces at
        trade entry): the z-score's peer population is the current run's universe - if that
        includes sub-floor nanocaps, their more extreme ratios distort the boundaries real,
        investable companies get ranked against. Sub-floor symbols simply aren't included in
        this pass and keep whatever Pass-1 already gave them.

        Raises on failure, same as every other post_run() batch pass - an inconsistent
        quality_score is a live-trading-relevant correctness issue.
        """
        try:
            with _owner().DatabaseContext("write") as cur:
                # ACTIVE-UNIVERSE GUARD (added 2026-09-09, migration 1276's own code fix - see
                # NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE's own module-level comment in
                # utils/loaders/helpers.py for the full evidence trail). This batch pass
                # previously scanned every quality_metrics row with a non-null quality_score,
                # with no check the symbol still belongs to the active, non-fund scored universe
                # get_active_symbols(exclude_etfs=True) already enforces for the per-symbol fetch
                # path - a closed-end fund/BDC/trust whose row predates that exclusion kept
                # getting its sector-neutral z-score freshly recomputed here forever (live-
                # confirmed RGT held the single highest quality_score in the entire universe).
                cur.execute(
                    """
                    SELECT qm.symbol, cp.sector, cp.industry, qm.roe, qm.roa, qm.roce_pct, qm.fcf_margin,
                           qm.debt_to_equity, qm.margin_volatility, qm.asset_turnover, qm.gross_profitability,
                           qm.quality_score, COALESCE(cis.is_foreign_private_issuer, false), vm.market_cap,
                           qm.earnings_variability
                    FROM quality_metrics qm
                    JOIN stock_scores ss ON ss.symbol = qm.symbol
                    LEFT JOIN company_profile cp ON cp.symbol = qm.symbol
                    JOIN stock_symbols su ON su.symbol = qm.symbol
                    LEFT JOIN company_info_sec cis ON cis.symbol = qm.symbol
                    LEFT JOIN value_metrics vm ON vm.symbol = qm.symbol
                    """
                    + LIQUIDITY_FLOOR_JOIN_SQL
                    + """
                    WHERE qm.quality_score IS NOT NULL
                      AND COALESCE(qm.data_unavailable, false) = false
                      AND liq_floor.latest_close >= %s
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
                logger.warning(
                    "[QUALITY_METRICS] update_quality_sector_neutral_scores: no eligible rows found - skipping."
                )
                return

            # Sector peer group for the COMPOSITE's sector-relative step (MSCI Appendix VI) - a
            # symbol with no company_profile.sector row simply has no entry here, which
            # sector_neutral_zscore() pools into its residual group rather than dropping (see
            # that function's own docstring). Mortgage/commercial-mortgage REITs are split out
            # of "Real Estate" into their own peer group (see apply_mortgage_reit_sector_
            # override's docstring in vqg_shared.py) - found 2026-09-12 while investigating why
            # the live REIT leaderboard topped mortgage REITs (DX/ORC/NLY/AGNC) instead of real
            # REIT industry leaders.
            sectors: dict[str, str] = {
                row[0]: (apply_mortgage_reit_sector_override(row[0], row[1]) or row[1]) for row in rows if row[1]
            }

            # FPI peer-group split (2026-09-14, goal-session "fix z-scoring issues" directive -
            # see sector_neutral_zscore's own docstring in factor_normalization.py for the full
            # rationale/evidence). row[12] is COALESCE(cis.is_foreign_private_issuer, false) per
            # this query's own SELECT above - len(row) guard keeps pre-existing shorter unit-test
            # fixture rows passing unchanged.
            is_fpi: dict[str, bool] = {row[0]: bool(row[12]) for row in rows if len(row) > 12}

            def _negated_raw(idx: int) -> dict[str, float]:
                # "Lower is better" variables (Debt to Equity, Earnings Variability): negate
                # before z-scoring so a higher z always means better quality, matching ROE's
                # own direction.
                return {row[0]: -float(row[idx]) for row in rows if row[idx] is not None}

            # roe additionally requires roa present/non-negative (sign-flip distress guard,
            # see this method's own docstring) - roa itself is NOT a scored MSCI variable, read
            # here purely as that data-quality gate.
            roe_raw = {
                row[0]: float(row[3])
                for row in rows
                if row[3] is not None and row[4] is not None and float(row[3]) >= 0.0 and float(row[4]) >= 0.0
            }
            d2e_raw = _negated_raw(7)
            earnings_var_raw = _negated_raw(14)

            # STEP 1 (MSCI Appendix I/II): z-score EACH variable UNIVERSE-WIDE (within the
            # whole eligible universe, "the MSCI Parent Index" - NOT per-sector).
            leg_roe_z = universe_wide_zscore(roe_raw)
            leg_d2e_z = universe_wide_zscore(d2e_raw)
            leg_earnings_var_z = universe_wide_zscore(earnings_var_raw)
            logger.info(
                f"[QUALITY_METRICS] MSCI z-score universe: roe={len(leg_roe_z)} "
                f"debt_to_equity={len(leg_d2e_z)} earnings_variability={len(leg_earnings_var_z)}"
            )

            # STEP 2: equal-weighted composite, ROE MANDATORY (Appendix II Cases 1/4 - see this
            # method's own docstring), D/E or Earnings Variability alone still scores (Cases
            # 2/3). Distress floors use -3.0 (MSCI's own winsorization bound, the natural
            # "worst" sentinel) rather than an arbitrary number - same convention Value's
            # rebuild established.
            composite_z_by_symbol: dict[str, float] = {}
            for row in rows:
                symbol = row[0]
                roe, roa, d2e = row[3], row[4], row[7]
                roe_is_sign_flip_distress = (
                    roe is not None and roa is not None and (float(roe) < 0.0 or float(roa) < 0.0)
                )
                if roe_is_sign_flip_distress:
                    roe_z: float | None = -3.0
                elif symbol in leg_roe_z:
                    roe_z = leg_roe_z[symbol]
                else:
                    roe_z = None  # ROE genuinely missing (not just sign-flip-floored) -> no score at all
                if roe_z is None:
                    continue
                legs: list[float] = [roe_z]
                if symbol in leg_d2e_z:
                    legs.append(-3.0 if float(d2e) < 0.0 else leg_d2e_z[symbol])  # negative D/E = real distress
                if symbol in leg_earnings_var_z:
                    legs.append(leg_earnings_var_z[symbol])
                composite_z_by_symbol[symbol] = sum(legs) / len(legs)

            # STEP 3: sector-relativize the COMPOSITE (not each variable individually, and only
            # once) - MSCI's real "Sector Neutral Quality Index" construction (Appendix VI) -
            # then winsorize at +/-3, MSCI's own stated output bound.
            sector_rel_z = sector_neutral_zscore(
                composite_z_by_symbol, sectors, min_sector_size=15, is_foreign_private_issuer=is_fpi
            )
            sector_rel_z = {symbol: max(-3.0, min(3.0, z)) for symbol, z in sector_rel_z.items()}
            quality_pct = zscore_to_percentile_scale(sector_rel_z)
            logger.info(f"[QUALITY_METRICS] MSCI composite scored, sector-relativized: {len(quality_pct)} symbols")

            updates: list[tuple[str, float | None]] = []
            for row in rows:
                symbol, quality_score_old = row[0], float(row[11])
                if symbol not in quality_pct:
                    continue
                quality_score_new = round(max(0.0, min(100.0, quality_pct[symbol])), 2)
                if quality_score_new != quality_score_old:
                    updates.append((symbol, quality_score_new))

            updates.extend(self._withhold_quality_below_floor())

            if not updates:
                logger.info("[QUALITY_METRICS] sector-neutral z-score pass: no eligible symbols to update.")
                return

            with _owner().DatabaseContext("write") as cur:
                # ::numeric cast (added alongside _withhold_quality_below_floor(), 2026-09-15):
                # quality_score is now NULL for withheld rows in the same batch as real floats
                # from the correction loop above - same mixed-None/float wrong-inferred-column-
                # type psycopg2 gotcha already hit and fixed for momentum_score/quality_score
                # in stock_scores (see quality_scoring.py's update_quality_from_source()).
                _owner().execute_values(
                    cur,
                    """
                    UPDATE quality_metrics AS qm
                    SET quality_score = v.quality_score::numeric,
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
