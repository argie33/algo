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
from typing import Any

from loaders.helpers.factor_normalization import (
    universe_wide_zscore,
    zscore_to_percentile_scale,
)
from loaders.helpers.vqg_quality_debt_fallback import DebtComponentsFallbackMixin
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

    @staticmethod
    def _accumulate_qmj_leg_sums(
        rows: list[tuple[Any, ...]],
        z_gpoa: dict[str, float],
        z_gmar: dict[str, float],
        z_acc: dict[str, float],
        z_cfoa: dict[str, float],
        z_roa: dict[str, float],
        z_roe: dict[str, float],
        z_roe_trend: dict[str, float],
        z_gmar_trend: dict[str, float],
        z_leverage: dict[str, float],
        z_earnings_var: dict[str, float],
        z_payout: dict[str, float],
    ) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, float]]:
        """Extracted from update_quality_sector_neutral_scores (2026-09-17, C901 complexity
        gate) - pure extraction, no behavior change. STEP 1's per-symbol leg-summing loop: for
        each of the 4 QMJ legs (Profitability/Growth/Safety/Payout), sum whichever raw z-scored
        sub-components that symbol has (see the caller's own docstring for the sign-flip-
        distress/negative-book-equity floor handling on the Profitability/Safety legs).
        Returns (profitability_sum, growth_sum, safety_sum, payout_sum).
        """

        def _leg_sum_z(symbol: str, components: list[dict[str, float]]) -> float | None:
            vals = [c[symbol] for c in components if symbol in c]
            if not vals:
                return None
            return sum(vals)

        profitability_sum: dict[str, float] = {}
        growth_sum: dict[str, float] = {}
        safety_sum: dict[str, float] = {}
        payout_sum: dict[str, float] = {}
        for row in rows:
            symbol, roe, roa = row[0], row[1], row[2]
            roe_is_sign_flip_distress = roe is not None and roa is not None and (float(roe) < 0.0 or float(roa) < 0.0)
            profitability_components = [z_gpoa, z_gmar, z_acc, z_cfoa, z_roa]
            p_sum = _leg_sum_z(symbol, profitability_components) or 0.0
            p_count = sum(1 for c in profitability_components if symbol in c)
            if roe_is_sign_flip_distress:
                p_sum += -3.0
                p_count += 1
            elif symbol in z_roe:
                p_sum += z_roe[symbol]
                p_count += 1
            if p_count > 0:
                profitability_sum[symbol] = p_sum

            g_sum = _leg_sum_z(symbol, [z_roe_trend, z_gmar_trend])
            if g_sum is not None:
                growth_sum[symbol] = g_sum

            d2e = row[3]
            s_sum = _leg_sum_z(symbol, [z_earnings_var]) or 0.0
            s_count = 1 if symbol in z_earnings_var else 0
            if d2e is not None and float(d2e) < 0.0:
                s_sum += -3.0  # negative book equity - real distress, not "zero leverage"
                s_count += 1
            elif symbol in z_leverage:
                s_sum += z_leverage[symbol]
                s_count += 1
            if s_count > 0:
                safety_sum[symbol] = s_sum

            if symbol in z_payout:
                payout_sum[symbol] = z_payout[symbol]

        return profitability_sum, growth_sum, safety_sum, payout_sum

    def update_quality_sector_neutral_scores(self) -> None:
        """Batch pass: FULLY RECOMPUTE quality_score from scratch off the raw stored ratio
        columns (not patched relative to whatever quality_score currently holds), for every
        scored symbol - mirrors `update_rs_percentiles()`'s pure-overwrite pattern, NOT
        `update_value_multiples_percentiles()`'s additive-delta one.

        REBUILT TO AQR'S REAL QUALITY MINUS JUNK (QMJ) FRAMEWORK 2026-09-17 (factor-purity
        pivot: MSCI -> AQR only, user directive - "we are not using industry standard AQR
        yet for all the factors... get rid of the msci and all this other shit"). SUPERSEDES
        the MSCI 3-variable Quality Index rebuild (ROE/Debt-to-Equity/Earnings-Variability,
        2026-09-16 - see git history for that version, itself a real, correctly-cited MSCI
        construction, just MSCI rather than AQR). Fetched and read Asness/Frazzini/Pedersen
        2019 "Quality Minus Junk" directly this session (papers.ssrn.com/abstract=2312432;
        econ.yale.edu/~shiller/behfin/2013_04-10/asness-frazzini-pedersen.pdf) - not recalled/
        paraphrased: "we...use a broad set of proxies to define four composite proxies:
        Profitability, Growth, Safety and Payout... Quality is defined by means of variables
        motivated by the Gordon growth model." Construction (mirrors this codebase's own
        established z-of-z pattern - see e.g. Value's update_value_multiples_percentiles()):
          1. z-score EACH available raw sub-component UNIVERSE-WIDE (`universe_wide_zscore`) -
             "lower is better" ones (leverage, earnings variability, accruals) negated first so
             a higher z always means higher quality.
          2. Each of the 4 legs (Profitability/Growth/Safety/Payout) = SUM of its available
             sub-component z-scores, re-standardized universe-wide once more - the paper's own
             two-stage construction (z-score raw variables, sum, re-standardize to form each
             composite proxy), not a simple average.
          3. quality_score = SUM of the available leg z-scores, re-standardized universe-wide
             ONE more time, winsorized at +/-3 (kept as a real published normalization tail
             treatment, not MSCI-index-specific - every z-score pillar in this codebase does
             this), then mapped to [0,100] via zscore_to_percentile_scale (same normal-CDF
             transform every other pillar uses, not the QMJ paper's own portfolio-sort
             mechanics - see Value's rebuild docstring for why a rating scale and a portfolio
             weight are different domains).

        LEG COMPONENTS - what's genuinely available in this schema, what isn't (see this
        method's own precedent for "no substitute shipped for a descriptor this system can't
        actually compute" - growth_scoring.py's forward_eps_growth_next_fy note):
          - PROFITABILITY (paper: GPOA, ROE, ROA, CFOA, GMAR, low accruals) - FULLY available:
            gross_profitability (GPOA, gross_profit/assets), roe, roa, gross_margin (GMAR),
            and CFOA (operating_cash_flow/assets) derived algebraically from two already-
            stored ratios - roa - accruals_ratio = (NI/Assets) - (NI-OCF)/Assets = OCF/Assets -
            no new query needed. Accruals (ACC, NI-OCF over assets) is negated (low ACC =
            good, matching the paper's "low accruals" framing).
          - GROWTH (paper: 5-year CHANGE in each Profitability measure) - PARTIAL: this
            schema has no stored 5-year GPOA/ROA/CFOA/ACC growth series, only two real 5-year-
            style OLS trend fields already computed for the (now-retired, see
            pillar_weights.py) Growth pillar - growth_metrics.roe_trend (trend in ROE) and
            growth_metrics.gross_margin_trend (trend in GMAR). Used as-is; GPOA-growth/ROA-
            growth/CFOA-growth/ACC-growth are NOT computed anywhere in this DB and are
            genuinely omitted, not faked with a substitute.
          - SAFETY (paper: low beta, low leverage, low earnings volatility, low bankruptcy
            risk) - beta DELIBERATELY EXCLUDED: this repo's own Risk pillar (risk_scoring.py)
            is ALREADY Frazzini-Pedersen's own Betting-Against-Beta shrinkage beta, computed
            the same session - reusing (or re-deriving) the identical beta signal here would
            double-count the same information across 2 of only 4 top-level pillars, which is a
            real, deliberate architecture choice, not an oversight. Uses debt_to_equity
            (negated, low leverage) and earnings_variability (negated, low vol) - both already
            computed for the prior MSCI construction. Bankruptcy risk (Altman Z''/Ohlson
            O-score) is NOT scored here either - same reasoning vqg_quality_score.py's own
            comment already gives for Altman Z: a discrete distress-triage classifier in the
            literature, not meant to be continuously averaged into a magnitude-weighted
            composite (a genuinely-computed continuous distress score isn't in this DB anyway).
          - PAYOUT (paper: -net equity issuance, -net debt issuance, dividend/net-income
            payout ratio, averaged) - PARTIAL: this schema doesn't track multi-year net
            share-count or net-debt CHANGE (issuance/buyback deltas), so the paper's exact
            3-component average can't be built. value_metrics.net_payout_yield (dividends +
            buybacks, market-cap-scaled - a real, already-computed "returns capital to
            shareholders" measure, just yield-scaled rather than the paper's book-value-scaled
            issuance measure) is used as the sole Payout leg component - the closest genuinely
            real proxy available, not an invented one.

        Sign-flip distress guard (unchanged from the prior MSCI version, still the correct
        data-quality gate regardless of which factor model consumes ROE): a negative-ROA
        (loss-making) company can only show a POSITIVE ROE when shareholders_equity is ALSO
        negative - not genuine profitability. ROE's own z-contribution is floored to -3.0 (the
        same winsorization bound used everywhere else in this codebase as the "worst"
        sentinel) when roe<0 OR roa<0; roa itself is not separately scored beyond this guard.

        INVESTABILITY FLOOR: same liquidity-floor mechanism (`liq_floor.latest_close`/
        `liq_floor.avg_dollar_volume_20d`) every sibling pillar's batch pass uses - sub-floor
        symbols aren't included in this pass and keep whatever Pass-1 already gave them.

        MUST be a pure function of the raw stored ratio columns, never reading quality_score
        itself as an input - same non-negotiable idempotency property as every sibling batch
        pass (see this method's own prior "additive-delta" bug history in git for why).

        Raises on failure, same as every other post_run() batch pass - an inconsistent
        quality_score is a live-trading-relevant correctness issue.
        """
        try:
            with _owner().DatabaseContext("write") as cur:
                # ACTIVE-UNIVERSE GUARD (added 2026-09-09, migration 1276's own code fix - see
                # NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE's own module-level comment in
                # utils/loaders/helpers.py for the full evidence trail).
                cur.execute(
                    """
                    SELECT qm.symbol, qm.roe, qm.roa, qm.debt_to_equity, qm.quality_score,
                           qm.earnings_variability, qm.gross_profitability, qm.gross_margin,
                           qm.accruals_ratio, gm.roe_trend, gm.gross_margin_trend,
                           vm.net_payout_yield
                    FROM quality_metrics qm
                    JOIN stock_scores ss ON ss.symbol = qm.symbol
                    JOIN stock_symbols su ON su.symbol = qm.symbol
                    LEFT JOIN company_info_sec cis ON cis.symbol = qm.symbol
                    LEFT JOIN growth_metrics gm ON gm.symbol = qm.symbol
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

            def _raw(idx: int, *, negate: bool = False) -> dict[str, float]:
                sign = -1.0 if negate else 1.0
                return {row[0]: sign * float(row[idx]) for row in rows if row[idx] is not None}

            # PROFITABILITY sub-components (indices per the SELECT above: 6=gross_profitability,
            # 7=gross_margin, 8=accruals_ratio; roe/roa handled separately below for the
            # sign-flip guard; cfoa derived algebraically, not a stored column).
            gpoa_raw = _raw(6)
            gmar_raw = _raw(7)
            acc_raw = _raw(8, negate=True)  # low accruals = good
            cfoa_raw = {
                row[0]: float(row[2]) - float(row[8]) for row in rows if row[2] is not None and row[8] is not None
            }
            # roe requires roa present/non-negative (sign-flip distress guard - see docstring).
            roe_raw = {
                row[0]: float(row[1])
                for row in rows
                if row[1] is not None and row[2] is not None and float(row[1]) >= 0.0 and float(row[2]) >= 0.0
            }
            roa_raw = {row[0]: float(row[2]) for row in rows if row[2] is not None}

            # GROWTH sub-components (9=roe_trend, 10=gross_margin_trend).
            roe_trend_raw = _raw(9)
            gmar_trend_raw = _raw(10)

            # SAFETY sub-components (3=debt_to_equity, 5=earnings_variability) - both negated,
            # "lower is better". Beta deliberately excluded - see docstring.
            #
            # Negative debt_to_equity (negative book equity - real financial distress, not
            # "great, zero leverage") is EXCLUDED from the normal negate-and-z-score treatment
            # and instead floored to -3.0 directly in the per-symbol loop below - same
            # distress-floor pattern the prior MSCI construction used and Value's own
            # negative-book-value floor uses. Only non-negative D/E values are z-scored here.
            leverage_raw = {row[0]: -float(row[3]) for row in rows if row[3] is not None and float(row[3]) >= 0.0}
            earnings_var_raw = _raw(5, negate=True)

            # PAYOUT sub-component (11=net_payout_yield, from value_metrics).
            payout_raw = _raw(11)

            # STEP 1: z-score every raw sub-component UNIVERSE-WIDE.
            z_gpoa = universe_wide_zscore(gpoa_raw)
            z_gmar = universe_wide_zscore(gmar_raw)
            z_acc = universe_wide_zscore(acc_raw)
            z_cfoa = universe_wide_zscore(cfoa_raw)
            z_roe = universe_wide_zscore(roe_raw)
            z_roa = universe_wide_zscore(roa_raw)
            z_roe_trend = universe_wide_zscore(roe_trend_raw)
            z_gmar_trend = universe_wide_zscore(gmar_trend_raw)
            z_leverage = universe_wide_zscore(leverage_raw)
            z_earnings_var = universe_wide_zscore(earnings_var_raw)
            z_payout = universe_wide_zscore(payout_raw)

            profitability_sum, growth_sum, safety_sum, payout_sum = self._accumulate_qmj_leg_sums(
                rows,
                z_gpoa,
                z_gmar,
                z_acc,
                z_cfoa,
                z_roa,
                z_roe,
                z_roe_trend,
                z_gmar_trend,
                z_leverage,
                z_earnings_var,
                z_payout,
            )

            # STEP 2: re-standardize each leg's raw sum universe-wide to form the leg's own
            # z-score composite (the paper's own two-stage construction).
            leg_profitability_z = universe_wide_zscore(profitability_sum)
            leg_growth_z = universe_wide_zscore(growth_sum)
            leg_safety_z = universe_wide_zscore(safety_sum)
            leg_payout_z = universe_wide_zscore(payout_sum)
            logger.info(
                f"[QUALITY_METRICS] AQR QMJ legs: profitability={len(leg_profitability_z)} "
                f"growth={len(leg_growth_z)} safety={len(leg_safety_z)} payout={len(leg_payout_z)}"
            )

            # quality_min_legs_available: same thin-sample-extrapolation principle as every
            # other minimum-coverage floor in this codebase (GROWTH_MIN_FIELDS_AVAILABLE,
            # VALUE_MIN_WEIGHT, min_quality_weight_pct in vqg_quality_score.py) - a symbol
            # scored off a single QMJ leg (of 4) is a thinner sample than one scored off all 4,
            # and shouldn't renormalize up to a full-confidence score.
            quality_min_legs_available = 2
            composite_sum_by_symbol: dict[str, float] = {}
            legs_available_by_symbol: dict[str, int] = {}
            for row in rows:
                symbol = row[0]
                legs = [leg_profitability_z, leg_growth_z, leg_safety_z, leg_payout_z]
                available = [leg[symbol] for leg in legs if symbol in leg]
                if len(available) >= quality_min_legs_available:
                    composite_sum_by_symbol[symbol] = sum(available)
                    legs_available_by_symbol[symbol] = len(available)

            # STEP 3: re-standardize the composite universe-wide ONE more time, winsorize at
            # +/-3 (real published normalization tail treatment, applied by every z-score
            # pillar in this codebase), map to [0,100].
            universe_z = universe_wide_zscore(composite_sum_by_symbol)
            universe_z = {symbol: max(-3.0, min(3.0, z)) for symbol, z in universe_z.items()}
            quality_pct = zscore_to_percentile_scale(universe_z)
            logger.info(f"[QUALITY_METRICS] AQR QMJ composite scored, universe-wide: {len(quality_pct)} symbols")

            updates: list[tuple[str, float | None]] = []
            for row in rows:
                symbol, quality_score_old = row[0], float(row[4])
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
