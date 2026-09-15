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

from loaders.helpers.factor_normalization import sector_size_neutral_zscore, zscore_to_percentile_scale
from loaders.helpers.vqg_quality_debt_fallback import DebtComponentsFallbackMixin
from loaders.helpers.vqg_shared import BROKER_DEALER_INDUSTRIES, apply_mortgage_reit_sector_override
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

        Non-negative-domain metrics were historically floored to 0.0 for negative values
        (matching Pass-1 `_margin_curve`'s `if value < 0: return 0.0`) - justified by ROE's
        sign-flip artifact (below), then copied onto the rest without checking each needed it.

        FLOOR REMOVED FOR roa/roce/fcf_margin ONLY (2026-09-13, evidence trail in memory:
        quality_roa_roce_fcf_margin_floor_removed_20260913) - a real point-in-time panel test
        shows continuous z-scoring (negatives included) beats the floor on era-robust
        forward-return prediction for these 3. debt_to_equity's apparently bigger gap was
        RETRACTED (test-script sign bug) - floor UNCHANGED there, and for gross_profitability
        (no material difference) and margin_volatility/asset_turnover (untested). ROE keeps
        its own floor/sign-flip guard (independent justification, not the copied pattern here).

        Sign-flip distress guard (live-confirmed 2026-09-07, 274 universe symbols, e.g. ROC
        roe=915.88%/roa=-38.43%): a negative-ROA (loss-making) company can only show a
        POSITIVE ROE when shareholders_equity is ALSO negative - a double-negative sign
        flip, not genuine profitability. The ROE component is omitted entirely if roa is
        missing, and floored to 0.0 (not z-scored) if roe<0 OR roa<0 - unchanged from the
        prior ROE/ROCE-only version of this method.

        INVESTABILITY FLOOR ADDED 2026-09-13 (`vm.market_cap >= %s`, algo_config.min_market_
        cap_millions, same $300M threshold LiquidityChecks._check_market_cap() now enforces at
        trade entry): the sector-neutral z-score's peer group is the current run's universe -
        if that includes sub-floor nanocaps, their more extreme ratios distort the percentile
        boundaries real, investable companies get ranked against. Sub-floor symbols simply
        aren't included in this pass and keep whatever Pass-1 already gave them.

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
                           qm.quality_score, COALESCE(cis.is_foreign_private_issuer, false), vm.market_cap
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

            # Sector peer group for the z-score - a symbol with no company_profile.sector row
            # simply has no entry here, which sector_neutral_zscore() pools into its residual
            # group rather than dropping (see that function's own docstring).
            # Mortgage/commercial-mortgage REITs are split out of "Real Estate" into their own
            # peer group (see apply_mortgage_reit_sector_override's docstring in vqg_shared.py) -
            # same "Real Estate" sector-conflation bug class as the FS bank/insurer carve-out
            # just below, found 2026-09-12 while investigating why the live REIT leaderboard
            # topped mortgage REITs (DX/ORC/NLY/AGNC) instead of real REIT industry leaders.
            sectors: dict[str, str] = {
                row[0]: (apply_mortgage_reit_sector_override(row[0], row[1]) or row[1]) for row in rows if row[1]
            }

            # FPI peer-group split (2026-09-14, goal-session "fix z-scoring issues" directive -
            # see sector_neutral_zscore's own docstring in factor_normalization.py for the full
            # rationale/evidence). row[12] is COALESCE(cis.is_foreign_private_issuer, false) per
            # this query's own SELECT above - len(row) guard keeps pre-existing shorter unit-test
            # fixture rows passing unchanged (same fail-open convention `industries` above uses).
            is_fpi: dict[str, bool] = {row[0]: bool(row[12]) for row in rows if len(row) > 12}

            # BARRA-STYLE SIZE NEUTRALIZATION (2026-09-15, "get rid of the extra shit beyond
            # Barra and the industry guys" directive - consistency follow-up to the same fix
            # already applied to Value/Growth, see sector_size_neutral_zscore's own docstring).
            # Real Barra/Axioma multi-factor construction regresses every style factor
            # (Quality included) on sector dummies + log market cap before z-scoring, not just
            # Value/Growth - AQR's published QMJ methodology doesn't do this size step at all,
            # but this codebase already committed to the Barra convention elsewhere, so Quality
            # now matches rather than being the one pillar left on the older sector-only
            # transform. len(row) guard keeps pre-existing shorter unit-test fixture rows
            # passing unchanged (same fail-open convention as is_fpi above) - a missing
            # market_cap simply skips size-neutralization for that symbol (see
            # _residualize_on_log_market_cap's own pass-through-unchanged fallback).
            market_cap_map: dict[str, float] = {
                row[0]: float(row[13]) for row in rows if len(row) > 13 and row[13] is not None and float(row[13]) > 0
            }

            # D2E/ROA/ROCE/ROE/asset_turnover peer-group refinement (2026-09-08, quality_value_
            # sector_neutral_zscore_rewrite follow-up; extended 2026-09-11 - see
            # roe_asset_turnover_fs_coarse_peer_group_bias_20260911): the single "Financial
            # Services" GICS sector z-score bucket mixes deposit-funded banks, reserve-funded
            # insurers, and unregulated other-FS (asset managers, payment networks, brokers)
            # whose leverage and capital-efficiency profiles aren't comparable -
            # DEPOSITORY_BANK_INDUSTRIES/INSURANCE_UNDERWRITER_INDUSTRIES already carve out for
            # the Pass-1 curves in vqg_quality.py (banks/insurers understate leverage against
            # total_liabilities the same way against each other's capital structure).
            # ROE was originally left on the coarse sector alongside fcf_margin/margin_
            # volatility/gross_profitability, but it's the MOST leverage-sensitive of the group
            # (ROE = ROA x leverage multiplier) - live-measured 2026-09-11: coarse-FS-grouped
            # bank ROE averaged the 36.6th percentile (vs the split group's neutral 49.9th) and
            # asset_turnover showed the same 4-5x median gap between banks (structurally huge
            # balance sheets relative to revenue) and "Other FS" that originally justified the
            # ROA/ROCE/D2E split - both moved onto the same split peer group here. fcf_margin
            # doesn't need this: banks/insurers are excluded from its z-score population
            # entirely (see _fcf_excluded_industries below). margin_volatility/gross_
            # profitability's cross-bucket gap was weaker (outlier-driven, not median-driven)
            # and gross_profitability's tiny per-bucket bank/insurer sample (n=11/13) would fall
            # under sector_neutral_zscore's own min_sector_size=15 floor and residual-pool right
            # back out anyway - left on the coarse sector, not flagged.
            _fs_industry_peer_group: dict[str, str] = {
                symbol: (
                    "Financial Services - Banks"
                    if industry in _owner().DEPOSITORY_BANK_INDUSTRIES
                    else (
                        "Financial Services - Insurance"
                        if industry in _owner().INSURANCE_UNDERWRITER_INDUSTRIES
                        else "Financial Services - Other"
                    )
                )
                for symbol, sector, industry, *_ in rows
                if sector == "Financial Services"
            }
            d2e_roa_roce_sectors: dict[str, str] = {
                symbol: _fs_industry_peer_group.get(symbol, sector) for symbol, sector in sectors.items()
            }

            # fcf_margin exclusion (2026-09-08, absorbed from Pass-1's already-live-confirmed
            # fix - see vqg_quality_score.py's fcf_margin_score comment): depository banks,
            # insurance underwriters, regulated utilities, and broker-dealers
            # (BROKER_DEALER_INDUSTRIES added 2026-09-08, GS/MS live-confirmed) have
            # free_cash_flow dominated by loan/deposit/capex/repo-funding swings unrelated to
            # real operating profitability (JPM -81%, GS -81.02%, WFC -22.70%, NEE -42%
            # live-confirmed) - not distress, a structural artifact excluded from both the
            # z-score population and each excluded symbol's own component list (same "omit,
            # don't floor" treatment as missing data). See BROKER_DEALER_INDUSTRIES's own
            # comment in vqg_shared.py.
            _fcf_excluded_industries = (
                _owner().DEPOSITORY_BANK_INDUSTRIES
                | _owner().INSURANCE_UNDERWRITER_INDUSTRIES
                | _owner().UTILITY_INDUSTRIES
                | BROKER_DEALER_INDUSTRIES
            )
            # len(row) guard keeps pre-existing unit test fixtures (3-tuple/11-tuple rows, no
            # industry column) passing unchanged - a missing industry fails open to "no
            # exclusion", the same fail-open contract _get_symbol_industry's own docstring
            # documents. industry lives at row[2] in this query's own column order (see SELECT
            # above), not appended at the end.
            industries: dict[str, str] = {row[0]: row[2] for row in rows if len(row) > 2 and row[2]}

            def _nonneg_raw(idx: int) -> dict[str, float]:
                return {row[0]: float(row[idx]) for row in rows if row[idx] is not None and float(row[idx]) >= 0.0}

            def _negated_nonneg_raw(idx: int) -> dict[str, float]:
                # "lower is better" metrics: negate before z-scoring so a higher z always
                # means better quality, matching every other component's direction.
                return {row[0]: -float(row[idx]) for row in rows if row[idx] is not None and float(row[idx]) >= 0.0}

            def _continuous_raw(idx: int) -> dict[str, float]:  # no floor - see "FLOOR REMOVED" note above
                return {row[0]: float(row[idx]) for row in rows if row[idx] is not None}

            # roe additionally requires roa present/non-negative (sign-flip guard), floored
            # to 0.0 in the loop below - independent of roa's own component (continuous above).
            # roce_raw/asset_turnover_raw (and their z-scored *_pct dicts) REMOVED 2026-09-15 -
            # see the ASSET_TURNOVER + ROCE REMOVED ENTIRELY comment in the component-weighting
            # loop below for the full rationale. qm.roce_pct/qm.asset_turnover (row[5]/row[9])
            # are still SELECTed and displayed elsewhere - only the now-unused z-scoring here is
            # gone.
            roe_raw = {
                row[0]: float(row[3])
                for row in rows
                if row[3] is not None and row[4] is not None and float(row[3]) >= 0.0 and float(row[4]) >= 0.0
            }
            roa_raw = _continuous_raw(4)
            fcf_margin_raw = {
                symbol: val
                for symbol, val in _continuous_raw(6).items()
                if industries.get(symbol) not in _fcf_excluded_industries
            }
            d2e_raw = _negated_nonneg_raw(7)
            margin_vol_raw = _negated_nonneg_raw(8)
            gross_prof_raw = _nonneg_raw(10)

            roe_pct = zscore_to_percentile_scale(
                sector_size_neutral_zscore(
                    roe_raw, d2e_roa_roce_sectors, market_cap_map, is_foreign_private_issuer=is_fpi
                )
            )
            roa_pct = zscore_to_percentile_scale(
                sector_size_neutral_zscore(
                    roa_raw, d2e_roa_roce_sectors, market_cap_map, is_foreign_private_issuer=is_fpi
                )
            )
            fcf_margin_pct = zscore_to_percentile_scale(
                sector_size_neutral_zscore(fcf_margin_raw, sectors, market_cap_map, is_foreign_private_issuer=is_fpi)
            )
            d2e_pct = zscore_to_percentile_scale(
                sector_size_neutral_zscore(
                    d2e_raw, d2e_roa_roce_sectors, market_cap_map, is_foreign_private_issuer=is_fpi
                )
            )
            margin_vol_pct = zscore_to_percentile_scale(
                sector_size_neutral_zscore(margin_vol_raw, sectors, market_cap_map, is_foreign_private_issuer=is_fpi)
            )
            gross_prof_pct = zscore_to_percentile_scale(
                sector_size_neutral_zscore(gross_prof_raw, sectors, market_cap_map, is_foreign_private_issuer=is_fpi)
            )
            logger.info(
                f"[QUALITY_METRICS] sector-neutral z-score universe: roe={len(roe_pct)} roa={len(roa_pct)} "
                f"fcf_margin={len(fcf_margin_pct)} debt_to_equity={len(d2e_pct)} "
                f"margin_volatility={len(margin_vol_pct)} gross_profitability={len(gross_prof_pct)}"
            )

            updates: list[tuple[str, float | None]] = []
            for row in rows:
                symbol, quality_score_old = row[0], float(row[11])
                # roce_pct_val/asset_turnover (row[5]/row[9]) unpacked but intentionally unused -
                # see the ASSET_TURNOVER + ROCE REMOVED comment below.
                roe, roa, _roce_pct_val, fcf_margin, d2e, margin_vol, _asset_turnover, gross_prof = row[3:11]

                components: list[tuple[float, float]] = []

                # ASSET_TURNOVER + ROCE REMOVED ENTIRELY (2026-09-15, TWO-LAYER VALIDATION
                # POLICY - see vqg_quality_score.py Pass-1's own comment on its
                # quality_components list for the full rationale: neither maps to a real
                # institutional Quality definition (AQR QMJ/MSCI/Novy-Marx), unlike the
                # remaining 6 components, so they're dropped rather than reweighted based on
                # this repo's own IC - the wrong bar for a pillar-fidelity question. The
                # remaining 5 non-margin_volatility components move from 11.54 to 15.0 each
                # (75/5) to keep the already-decided 75-point non-margin_volatility pool
                # exactly matching its own total; margin_volatility stays at 25.0. Mirrors
                # vqg_quality_score.py Pass-1's own weights exactly - keep both passes' in
                # sync if either changes. roce_pct_val/asset_turnover are still read from
                # `row` above (unpacking stays aligned to the SELECT's column order) but no
                # longer feed a component here - both raw columns remain available for other
                # consumers via quality_metrics itself.
                if roe is not None and roa is not None:  # roa<0 = sign-flip distress artifact; missing roa omits it
                    roe_component = 0.0 if float(roe) < 0.0 or float(roa) < 0.0 else roe_pct[symbol]
                    components.append((roe_component, 15.0))
                if roa is not None:  # continuous, no floor
                    components.append((roa_pct[symbol], 15.0))
                if fcf_margin is not None and industries.get(symbol) not in _fcf_excluded_industries:
                    components.append((fcf_margin_pct[symbol], 15.0))  # continuous, no floor
                if d2e is not None:  # negative D/E = real distress, floored to 0.0 - UNCHANGED
                    d2e_component = 0.0 if float(d2e) < 0.0 else d2e_pct[symbol]
                    components.append((d2e_component, 15.0))
                if margin_vol is not None:
                    # Volatility can't be genuinely negative - no floor case, just z-scored.
                    components.append((margin_vol_pct[symbol], 25.0))
                if gross_prof is not None:
                    gp_component = 0.0 if float(gross_prof) < 0.0 else gross_prof_pct[symbol]
                    components.append((gp_component, 15.0))

                # COMPLETENESS FLOOR (2026-09-10 real-money-readiness re-audit): mirrors
                # vqg_quality_score.py's Pass-1 `min_quality_weight_pct=40.0` floor on the
                # identical 8-component/101-point weight scheme. Without it, a symbol that
                # legitimately clears Pass-1's 40% floor (e.g. via ROE+ROA+ROCE+FCF-margin+
                # D/E) but has some of those individually None in THIS pass's stricter
                # inclusion rules (e.g. this pass's roe_component additionally requires roa
                # is not None, line 266 above) can fall below 40% available weight here and
                # still get a full sum(v*w)/total_weight extrapolated to 0-100 - unconditionally
                # overwriting Pass-1's more conservative (possibly None/insufficient-
                # completeness) score. Below the floor, skip the overwrite and leave whatever
                # Pass-1 already wrote (real score or None) untouched, same as this loop
                # already does for the total_weight<=0 case.
                total_weight = sum(w for _, w in components)
                if total_weight <= 0 or total_weight < 40.0:
                    continue

                quality_score_new = round(max(0.0, min(100.0, sum(v * w for v, w in components) / total_weight)), 2)
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
