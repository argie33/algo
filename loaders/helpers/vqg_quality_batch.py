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

# QUALITY_MIN_TOTAL_ASSETS (added 2026-09-19, /goal scores audit): materiality floor on
# invested capital for Quality's ROE-driven z-score population. Live-confirmed root cause:
# BUUU Group (quality_score=98.49, ranked #7 universe-wide alongside AAPL/LLY/MA/ADP/KLAC)
# has total_assets=$2.54M/stockholders_equity=$1.01M - 2-3 orders of magnitude below every
# other top-25 quality name (smallest peer, STRW, still has $878M total_assets) - against a
# $538M market cap, itself a thin-float pricing artifact, not a real large-scale operation.
# roe=78.7%/roa=31.25% are real arithmetic (net income / a near-worthless balance sheet), so
# the existing sign-flip distress guard (roe<0 or roa<0) never catches it - both legs are
# genuinely positive, just mechanically inflated by a denominator too small to be a
# meaningful "invested capital" base. This is the identical failure mode already fixed for
# royalty trusts/SPACs via NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE (a near-zero
# invested-capital balance sheet mechanically produces ratios no real operating company can
# match) - except BUUU is a genuine operating company (Cayman micro-cap, real SEC 10-K
# filer), so that SIC/name-based exclusion structurally can't catch it; this needs a direct
# materiality floor on the balance sheet itself instead.
# THRESHOLD: live-checked against the full quality-scored universe sorted by total_assets
# ascending - almost every symbol below $15M total_assets already scores quality_score<35
# on the merits (genuinely thin/distressed small caps, correctly low already) with BUUU the
# sole outlier landing near the top of the universe. $10M sits with wide margin below the
# smallest legitimate top-25 name (STRW $878M) and wide margin above BUUU's $2.54M, so it
# cleanly separates the one confirmed artifact from the rest of the real universe without
# touching genuinely-scored small/micro-caps whose low scores already reflect real weak
# fundamentals. Applied to total_assets specifically (not stockholders_equity) since a highly
# leveraged but real operating company can have small/negative equity on a large asset base -
# total_assets is the more robust "is this a real invested-capital base at all" gate.
QUALITY_MIN_TOTAL_ASSETS = 10_000_000.0

# Reusable LATERAL join fetching each symbol's latest total_assets - same "most recent fiscal
# year on file" convention already used throughout vqg_quality.py's own per-symbol fetch.
# NULL total_assets (data genuinely unavailable, e.g. some ADRs/foreign filers - see APAM/ITW
# in the live top-25 quality leaderboard, both real large caps with no total_assets on file)
# is NOT treated as a materiality failure - benefit of the doubt goes to "we don't have this
# data" rather than silently excluding a symbol this floor was never meant to catch. Only an
# EXPLICIT, present total_assets below the floor excludes a symbol.
QUALITY_MATERIALITY_JOIN_SQL = """
    LEFT JOIN LATERAL (
        SELECT total_assets
        FROM annual_balance_sheet
        WHERE symbol = qm.symbol
        ORDER BY fiscal_year DESC
        LIMIT 1
    ) qual_mat ON true
"""
QUALITY_MATERIALITY_FILTER_SQL = "(qual_mat.total_assets IS NULL OR qual_mat.total_assets >= %s)"


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
                + QUALITY_MATERIALITY_JOIN_SQL
                + """
                WHERE qm.quality_score IS NOT NULL
                  AND COALESCE(qm.data_unavailable, false) = false
                  AND (
                        liq_floor.latest_close IS NULL
                        OR liq_floor.latest_close < %s
                        OR liq_floor.avg_dollar_volume_20d IS NULL
                        OR liq_floor.avg_dollar_volume_20d < %s
                        OR NOT ("""
                + QUALITY_MATERIALITY_FILTER_SQL
                + """)
                        OR NOT ("""
                + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                + """)
                  )
                """,
                (
                    getattr(self, "_min_stock_price", None) or DEFAULT_MIN_STOCK_PRICE,
                    getattr(self, "_min_adv_dollars", None) or DEFAULT_MIN_ADV_DOLLARS,
                    QUALITY_MIN_TOTAL_ASSETS,
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
        scored symbol - mirrors `update_rs_percentiles()`'s pure-overwrite pattern, NOT
        `update_value_multiples_percentiles()`'s additive-delta one.

        RESTORED TO MSCI'S REAL 3-VARIABLE QUALITY INDEX 2026-09-17 (reverts the same-day AQR
        Quality Minus Junk (QMJ) pivot - see git history commit 4beaf7f1c for that version.
        Explicit user decision after a fresh audit compared this file against MSCI's real
        published Quality Indexes Methodology and found the AQR pivot had silently replaced it;
        user chose MSCI fidelity over AQR-purism for Value/Momentum/Quality, see
        pillar_weights.py's governance-comment block for the full record). MSCI's real
        3-step construction (identical shape to Value's own MSCI-formula rebuild - see
        loaders/stock_scores/value_metrics.py's update_value_multiples_percentiles() for the
        sibling implementation), fetched from msci.com/eqb/methodology/meth_docs/
        MSCI_Quality_Indexes_Methodology_May2022.pdf, Section 2.2 + Appendix I/II:
          1. z-score EACH of the 3 fundamental variables (Return on Equity, Debt to Equity,
             Earnings Variability - see loaders/helpers/quality_variability.py for the 3rd)
             UNIVERSE-WIDE (within the whole eligible universe, "the MSCI Parent Index" - NOT
             per-sector - see universe_wide_zscore below), market-cap-weighted per MSCI's real
             z-score formula. "Lower is better" variables (Debt to Equity, Earnings Variability)
             are negated before z-scoring so a higher z always means better quality, matching
             ROE's own direction.
          2. composite = equal-weighted average of the available variable z-scores (1/3 each,
             or 1/2 for the 2-of-3 substitution cases MSCI's Appendix II states - Cases 2/3).
             ROE IS MANDATORY (Appendix II Cases 1/4: missing ROE means no score at all, even
             if the other two are both present) - enforced explicitly, not just via a
             completeness floor.
          3. Re-standardize the COMPOSITE universe-wide (not per-sector - "measure the factor
             itself" directive, same choice already applied to Value's own rebuild the same
             session, see that method's own "STEP 3 SECTOR RELATIVIZATION REMOVED" docstring
             note for the full reasoning: MSCI's own sector step controls tracking error for a
             licensable ETF product, a portfolio-construction constraint, not a factor-
             measurement one), then winsorize at +/-3 - MSCI's own explicitly stated output
             bound.
        Final 0-100 conversion uses zscore_to_percentile_scale (the same normal-CDF transform
        this codebase already uses to bound every other z-score-based pillar/leg to [0,100]),
        not MSCI's own "Quality Score" piecewise transform (1+Z / (1-Z)^-1) - see Value's own
        rebuild docstring for why: that transform is a PORTFOLIO-WEIGHTING construction, not a
        rating scale, and stays reserved for algo/signals/market_cap_tilt.py's tilted-weight
        formula, its correct domain.

        DROPPED to match MSCI exactly: roa/fcf_margin/gross_profitability/accruals/CFOA (AQR
        QMJ Profitability-leg additions, not part of MSCI's 3-variable index), net_payout_yield
        (AQR QMJ Payout-leg stand-in) and growth_metrics.roe_trend/gross_margin_trend (AQR QMJ
        Growth-leg stand-in - moot anyway now that Growth is its own top-level
        BASE_PILLAR_WEIGHTS pillar again, see pillar_weights.py). All raw values stay
        computed/persisted/displayed - same "computed but unscored" convention as every other
        removed-from-scoring input elsewhere in this codebase - only their vote in
        quality_score is removed. The FS-bank/insurance/utility industry-split peer groups this
        method used at various points are not needed: MSCI's real construction z-scores each
        variable universe-wide (step 1), not per-sector at all.

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
        established) if roe<0 OR roa<0, unchanged reasoning from every prior version of this
        method.

        INVESTABILITY FLOOR: same liquidity-floor mechanism (`liq_floor.latest_close`/
        `liq_floor.avg_dollar_volume_20d`) every sibling pillar's batch pass uses - sub-floor
        symbols aren't included in this pass and keep whatever Pass-1 already gave them.

        MATERIALITY FLOOR (added 2026-09-19, /goal scores audit): total_assets >=
        QUALITY_MIN_TOTAL_ASSETS ($10M), NULLs exempted - see that constant's own docstring
        for the BUUU Group live finding (quality_score=98.49 off a $2.54M balance sheet,
        genuinely positive ROE/ROA so the sign-flip distress guard above never catches it).
        Same "sub-floor symbols excluded from this pass, withheld rather than left stale by
        _withhold_quality_below_floor()" treatment as the liquidity floor.

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
                           qm.earnings_variability, COALESCE(cis.is_foreign_private_issuer, false),
                           vm.market_cap
                    FROM quality_metrics qm
                    JOIN stock_scores ss ON ss.symbol = qm.symbol
                    JOIN stock_symbols su ON su.symbol = qm.symbol
                    LEFT JOIN company_info_sec cis ON cis.symbol = qm.symbol
                    LEFT JOIN value_metrics vm ON vm.symbol = qm.symbol
                    """
                    + LIQUIDITY_FLOOR_JOIN_SQL
                    + QUALITY_MATERIALITY_JOIN_SQL
                    + """
                    WHERE qm.quality_score IS NOT NULL
                      AND COALESCE(qm.data_unavailable, false) = false
                      AND liq_floor.latest_close >= %s
                      AND liq_floor.avg_dollar_volume_20d >= %s
                      AND """
                    + QUALITY_MATERIALITY_FILTER_SQL
                    + """
                      AND ("""
                    + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                    + ")",
                    (
                        getattr(self, "_min_stock_price", None) or DEFAULT_MIN_STOCK_PRICE,
                        getattr(self, "_min_adv_dollars", None) or DEFAULT_MIN_ADV_DOLLARS,
                        QUALITY_MIN_TOTAL_ASSETS,
                    ),
                )
                rows = cur.fetchall()

            if not rows:
                logger.warning(
                    "[QUALITY_METRICS] update_quality_sector_neutral_scores: no eligible rows found - skipping."
                )
                return

            # market_caps: MSCI's real z-score formula weights by free-float market cap, not
            # equal-weighted (see factor_normalization.py's universe_wide_zscore docstring).
            market_caps: dict[str, float] = {row[0]: float(row[7]) for row in rows if row[7] is not None}

            def _negated_raw(idx: int) -> dict[str, float]:
                # "Lower is better" variables (Debt to Equity, Earnings Variability): negate
                # before z-scoring so a higher z always means better quality, matching ROE's
                # own direction.
                return {row[0]: -float(row[idx]) for row in rows if row[idx] is not None}

            # roe additionally requires roa present/non-negative (sign-flip distress guard,
            # see this method's own docstring) - roa itself is NOT a scored MSCI variable, read
            # here purely as that data-quality gate.
            roe_raw = {
                row[0]: float(row[1])
                for row in rows
                if row[1] is not None and row[2] is not None and float(row[1]) >= 0.0 and float(row[2]) >= 0.0
            }
            d2e_raw = _negated_raw(3)
            earnings_var_raw = _negated_raw(5)

            # STEP 1 (MSCI Appendix I/II): z-score EACH variable UNIVERSE-WIDE (within the
            # whole eligible universe, "the MSCI Parent Index" - NOT per-sector), market-cap-
            # weighted.
            leg_roe_z = universe_wide_zscore(roe_raw, market_caps)
            leg_d2e_z = universe_wide_zscore(d2e_raw, market_caps)
            leg_earnings_var_z = universe_wide_zscore(earnings_var_raw, market_caps)
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
                roe, roa, d2e = row[1], row[2], row[3]
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

            # STEP 3: re-standardize the COMPOSITE universe-wide (not per-sector - see this
            # method's own docstring), then winsorize at +/-3, MSCI's own stated output bound.
            universe_z = universe_wide_zscore(composite_z_by_symbol, market_caps)
            universe_z = {symbol: max(-3.0, min(3.0, z)) for symbol, z in universe_z.items()}
            quality_pct = zscore_to_percentile_scale(universe_z)
            logger.info(f"[QUALITY_METRICS] MSCI composite scored, universe-wide: {len(quality_pct)} symbols")

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
                # in stock_scores.
                #
                # STOCK_SCORES IS NOW THE PRIMARY WRITE (2026-09-19 cleanup, user directive
                # "we want only what is in stock_scores... get rid of the messes"): this used
                # to write quality_metrics.quality_score ONLY, with a separate pass
                # (quality_scoring.py's update_quality_from_source()) copying that value into
                # stock_scores afterward - the one pillar computing its real score somewhere
                # OTHER than stock_scores, unlike Value/Growth/Risk/Momentum, each of which
                # writes stock_scores directly in their own batch pass. That backwards flow
                # was the literal mechanism behind a real divergence incident (up to 26pt drift
                # on 1,369 symbols incl. NVDA/MSFT/WMT/XOM/V/PG/NFLX - stock_scores kept a stale
                # copy whenever the sync pass didn't run on the same cadence as this one).
                # stock_scores.quality_score is now written directly here, matching every
                # sibling pillar; quality_metrics.quality_score becomes a read-only mirror of
                # this value (same direction loaders/stock_scores/value_metrics.py's own
                # value_score-into-value_metrics sync already uses), not the source of truth.
                _owner().execute_values(
                    cur,
                    """
                    UPDATE stock_scores AS ss
                    SET quality_score = v.quality_score::numeric,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (VALUES %s) AS v(symbol, quality_score)
                    WHERE ss.symbol = v.symbol
                    """,
                    updates,
                    template="(%s, %s)",
                )
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
