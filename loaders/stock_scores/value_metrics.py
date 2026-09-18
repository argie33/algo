"""ValueMetricsMixin, extracted from load_stock_scores.py (2026-09-05, file-size-ratchet
bloaters-decomposition split): the rest of the Value pillar (everything except _score_value
itself, which lives in loaders/stock_scores/value_score.py - see that module's docstring for
why it's separate). Moved verbatim - no behavior change - except `DatabaseContext(...)`/
`execute_values(...)` call sites in update_value_multiples_percentiles now go through
`_owner()` (see that helper's own docstring for why).

Mixed into StockScoresLoader alongside the other stock_scores/*.py pillar mixins - every
`self.`/`cls.` reference here (including `_MIN_SECTOR_SLICE`) resolves normally through the
instance regardless of which mixin file defines it.
"""

import json
import logging
from typing import TYPE_CHECKING, Any

import psycopg2

from loaders.helpers.factor_normalization import (
    universe_wide_zscore,
    zscore_to_percentile_scale,
)
from loaders.helpers.vqg_shared import (
    DEPOSITORY_BANK_INDUSTRIES,
    INSURANCE_UNDERWRITER_INDUSTRIES,
    apply_mortgage_reit_sector_override,
)
from loaders.stock_scores.pillar_weights import (
    BASE_PILLAR_WEIGHTS,
    DEFAULT_MIN_ADV_DOLLARS,
    DEFAULT_MIN_STOCK_PRICE,
    LIQUIDITY_FLOOR_JOIN_SQL,
)
from loaders.stock_scores.value_score import VALUE_MIN_WEIGHT
from utils.loaders.helpers import NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE
from utils.type_conversion import safe_float

logger = logging.getLogger("loaders.load_stock_scores")


def _owner() -> Any:
    """Lazy reference to the owner module, resolved at call time (not import time).

    Two reasons this indirection exists, both load-bearing (see loaders/helpers/vqg_quality.py's
    identical `_owner()` for the precedent this copies):
    (1) DatabaseContext/execute_values: several existing unit tests monkeypatch
    ``loaders.load_stock_scores.DatabaseContext``/``.execute_values`` directly. A module-level
    ``from utils.db.context import DatabaseContext`` here would bind this module's own separate
    copy of the name, which those patches can never reach - going through
    ``_owner().DatabaseContext`` always reads whatever the owner module's current attribute is,
    mocked or real.
    (2) Avoids importing anything from the owner module at THIS module's top level: when the
    owner is run as a script (``python loaders/load_stock_scores.py``) rather than imported as a
    package, it registers under ``sys.modules["__main__"]``, not its dotted path - a top-level
    `from loaders.load_stock_scores import X` here would then re-import the owner from scratch
    while it's still mid-import, before this class exists yet, raising ImportError (exactly the
    failure documented in vqg_and_stock_scores_dead_split_files_deleted_20260905 in memory).
    Importing lazily inside a function body sidesteps this entirely since it only runs after
    both modules have finished importing.
    """
    from loaders import load_stock_scores as _owner_mod

    return _owner_mod


class ValueMetricsMixin:
    """See module docstring.

    `_value_cache` is set on the instance by `_prepare_batch_context` (defined on
    StockScoresLoader itself, not any mixin) - declared type-checking-only below so mypy can
    see it without a real circular import.
    """

    if TYPE_CHECKING:
        _value_cache: dict[str, tuple[Any, ...]]

    def _get_value_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch value metrics for symbol.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 17 columns (pe_ratio, pb_ratio, ps_ratio, peg_ratio,
          dividend_yield, fcf_yield, forward_pe, ev_ebitda, ev_revenue, margin_of_safety_pct,
          market_cap, net_payout_yield, pe_ratio_unavailable_reason,
          forward_pe_unavailable_reason, pb_ratio_unavailable_reason,
          ps_ratio_unavailable_reason, data_unavailable) - the
          pe_ratio/forward_pe *_unavailable_reason columns were added 2026-08-28 to distinguish
          "genuinely missing data" from "unprofitable company / negative earnings forecast" for
          P/E and Forward P/E (see _score_value's "UNPROFITABLE-COMPANY FLOOR ADDED 2026-08-28"
          docstring note); pb_ratio_unavailable_reason added 2026-09-05 and
          ps_ratio_unavailable_reason added (real-money-readiness audit) for the identical
          negative-book-value/no-revenue cases, previously missing here entirely.
        - Schema mismatch (len(row) < 17) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_value_metrics_found"

        CRITICAL FIX 2026-07-01: Now checks data_unavailable flag. Some securities have rows
        marked data_unavailable=True with NULL values. Previously returned NULLs instead of
        marker; now properly returns marker dict.

        MINIMUM DATA REQUIREMENT: Row must have exactly 7 columns. Missing columns causes immediate
        fail-fast ValueError. Required metric for stock scoring (critical upstream loader).
        """
        row = self._value_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 15 columns before accessing indices
            # (11 + market_cap added 2026-08-25 to close the Size-factor gap, +1 more
            # net_payout_yield added 2026-08-26, +2 more pe_ratio_unavailable_reason/
            # forward_pe_unavailable_reason added 2026-08-28, +1 more pb_ratio_unavailable_reason
            # added 2026-09-05, +1 more ps_ratio_unavailable_reason added - see _score_value's
            # docstring)
            if len(row) < 17:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: value_metrics row has {len(row)} columns, expected 17. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[16]
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in value_metrics "
                    f"(likely security with missing pricing data)"
                )
                return {"symbol": symbol, "data_unavailable": True, "reason": "value_data_marked_unavailable"}
            # Row exists and data is available
            return {
                "pe_ratio": safe_float(row[0], f"{symbol}.pe_ratio"),
                "pb_ratio": safe_float(row[1], f"{symbol}.pb_ratio"),
                "ps_ratio": safe_float(row[2], f"{symbol}.ps_ratio"),
                "peg_ratio": safe_float(row[3], f"{symbol}.peg_ratio"),
                "dividend_yield": safe_float(row[4], f"{symbol}.dividend_yield"),
                "fcf_yield": safe_float(row[5], f"{symbol}.fcf_yield"),
                "forward_pe": safe_float(row[6], f"{symbol}.forward_pe", allow_none=True),
                "ev_ebitda": safe_float(row[7], f"{symbol}.ev_ebitda", allow_none=True),
                "ev_revenue": safe_float(row[8], f"{symbol}.ev_revenue", allow_none=True),
                "margin_of_safety_pct": safe_float(row[9], f"{symbol}.margin_of_safety_pct", allow_none=True),
                "market_cap": safe_float(row[10], f"{symbol}.market_cap", allow_none=True),
                "net_payout_yield": safe_float(row[11], f"{symbol}.net_payout_yield", allow_none=True),
                "pe_ratio_unavailable_reason": row[12],
                "forward_pe_unavailable_reason": row[13],
                "pb_ratio_unavailable_reason": row[14],
                "ps_ratio_unavailable_reason": row[15],
            }
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No value metrics available for {symbol} - score completeness will be reduced"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_metrics_found"}

    # NEUTRAL_PLACEHOLDER_SCORE (2026-09-17, factor-purity follow-up - "get rid of it," not just
    # verify it's inert). `_pe_curve_score`/`_pb_curve_score` used to be hand-set piecewise curves
    # (breakpoints at 10/20/35 for P/E, 1/3/7 for P/B) with no citation to any real methodology -
    # invented thresholds calibrated to nothing. Live-audited before removing them, not assumed
    # safe: reconstructed the exact curve output for every symbol with a real P/E in the current
    # universe (2,081 symbols) and diffed against the actual stored value_score (the real MSCI
    # Enhanced Value z-score composite, computed by update_value_multiples_percentiles() below) -
    # 18/2,081 landed within 0.5 points, and even those are coincidental correlation (P/E feeds
    # both formulas), not the curve surviving as the live score. `_withhold_value_below_floor()`
    # (below) independently confirms 0 symbols are currently stuck on Pass-1's value at all. The
    # curve's ENTIRE function is providing a non-NULL placeholder so (1) a symbol never shows a
    # blank value_score mid-run, before the batch pass below has run, and (2) update_value_
    # multiples_percentiles()'s own SELECT (`WHERE ss.value_score IS NOT NULL`) has a row to
    # correct in the first place - removing the placeholder mechanism entirely would break that
    # gate, not just "clean up" it. Since the curve's actual VALUE is proven to never be read as a
    # real score, inventing calibrated-looking breakpoints for it was pure theater - a flat,
    # explicitly-neutral placeholder does the identical plumbing job without pretending to encode
    # a methodology it doesn't. Genuine distress floors (unprofitable_stock/negative_forward_eps/
    # negative_book_value -> 0.0 in `_score_value`) are UNCHANGED - those are real sentinel values
    # matching Pass 2's own floor treatment, not calibrated curve breakpoints, and were never part
    # of this function.
    NEUTRAL_PLACEHOLDER_SCORE = 50.0

    @staticmethod
    def _pe_curve_score(_pe: float) -> float:
        """Pass-1 PLACEHOLDER ONLY for P/E - see NEUTRAL_PLACEHOLDER_SCORE's own docstring for
        why this is a flat neutral value, not a curve, as of 2026-09-17. Always overwritten by
        update_value_multiples_percentiles()'s real MSCI Enhanced Value z-score before any
        consumer reads it, except as a same-run fallback if that pass fails partway through -
        `_pe` is accepted (unused) only so existing call sites don't need updating."""
        return ValueMetricsMixin.NEUTRAL_PLACEHOLDER_SCORE

    @staticmethod
    def _pb_curve_score(_pb: float) -> float:
        """Pass-1 PLACEHOLDER ONLY for P/B - see `_pe_curve_score`'s docstring."""
        return ValueMetricsMixin.NEUTRAL_PLACEHOLDER_SCORE

    def _value_metrics_coverage_excluding_fpi(self, cur: Any) -> tuple[int, int] | None:
        """Return (covered, total) for value_metrics over the active, non-FPI universe.

        See audit_upstream_coverage()'s 2026-08-21 fix comment for why the raw
        data_loader_status.completion_pct is unusable for this gate: it counts every
        foreign-private-issuer symbol's permanent, correct value_metrics exclusion as a
        "failure" alongside genuine loader breakage.
        """
        try:
            cur.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE v.data_unavailable IS NOT TRUE) AS covered,
                  COUNT(*) AS total
                FROM value_metrics v
                JOIN stock_symbols s ON s.symbol = v.symbol
                LEFT JOIN LATERAL (
                    SELECT is_foreign_private_issuer FROM company_info_sec c
                    WHERE c.symbol = v.symbol ORDER BY filing_date DESC LIMIT 1
                ) cis ON true
                WHERE s.active = true AND COALESCE(cis.is_foreign_private_issuer, false) = false
                """
            )
            row = cur.fetchone()
            if not row or not row[1]:
                return None
            return int(row[0]), int(row[1])
        except Exception as e:
            logger.warning(f"[STOCK_SCORES] Could not compute FPI-excluded value_metrics coverage: {e}")
            return None

    @staticmethod
    def _percent_rank_cheap_high(values: dict[str, float]) -> dict[str, float]:
        """symbol -> percentile in [0, 100], where the LOWEST raw value gets the HIGHEST
        percentile (100) - matches this pillar's "cheap is good" convention for P/E, P/B, P/S.
        Ties share the same percentile (RANK()-style, not average-rank - matches PostgreSQL's
        own PERCENT_RANK() tie behavior, the same window function `update_rs_percentiles()`
        already uses for rs_percentile). A universe of 1 symbol gets 50.0 (no peer to rank
        against); no candidates to rank (empty input) returns {} - not an error, there is
        nothing to process.
        """
        n = len(values)
        if n == 0:
            return {}
        if n == 1:
            return dict.fromkeys(values, 50.0)
        sorted_items = sorted(values.items(), key=lambda kv: kv[1])
        result: dict[str, float] = {}
        i = 0
        while i < n:
            j = i
            while j < n and sorted_items[j][1] == sorted_items[i][1]:
                j += 1
            pct = 100.0 * (n - 1 - i) / (n - 1)
            for sym, _ in sorted_items[i:j]:
                result[sym] = pct
            i = j
        return result

    _MIN_SECTOR_SLICE = 20
    _WINSORIZE_MIN_GROUP_SIZE = 5

    @staticmethod
    def _winsorize_group_values(values: dict[str, float]) -> dict[str, float]:
        """Clip a group's raw values to its own [1st, 99th] percentile before ranking.

        FIX (2026-09-07, real-money-readiness leaderboard audit): `_percent_rank_cheap_high`/
        `_percent_rank_cheap_high_sector_relative` are pure rank transforms with no cross-check
        between metrics - the single most extreme raw value in a group always monopolized
        percentile 100 alone, even when the extremeness was a data/accounting artifact rather
        than genuine mispricing. Live-confirmed: VCIG's pb_ratio=0.01/ps_ratio=0.02, each the
        single cheapest in the whole 4,500+-symbol universe, won percentile 100/99.8 outright
        off that one observation.

        Below `_WINSORIZE_MIN_GROUP_SIZE`, an empirical quantile isn't a trustworthy clip
        boundary (too few points to estimate one reliably) - values pass through unchanged,
        same "too small to trust" precedent as `_MIN_SECTOR_SLICE`'s residual-pool fallback.
        Since this only clips, never reorders, non-extreme values are always untouched and
        ranking is otherwise rank-order-preserving except at the newly-shared boundary - two
        near-tied extreme peers now SHARE the top percentile instead of one arbitrarily
        winning it alone.

        Validated in `algo/research/value_percentile_rank_winsorization_test_20260907.py`
        (Fama-MacBeth + Spearman IC, fit 2017-2021 / holdout 2022-2026): winsorized-then-ranked
        is statistically indistinguishable from raw-then-ranked on every aggregate spec - this
        closes a real correctness gap at zero measured aggregate cost, not because it improved
        predictive power.
        """
        n = len(values)
        if n < ValueMetricsMixin._WINSORIZE_MIN_GROUP_SIZE:
            return dict(values)

        sorted_vals = sorted(values.values())

        def _percentile(pct: float) -> float:
            # Linear-interpolation percentile (matches numpy's default 'linear' method) -
            # no numpy dependency needed for a single-array quantile.
            rank = pct / 100.0 * (n - 1)
            lo = int(rank)
            hi = min(lo + 1, n - 1)
            frac = rank - lo
            return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac

        low = _percentile(1.0)
        high = _percentile(99.0)
        return {symbol: min(max(val, low), high) for symbol, val in values.items()}

    @classmethod
    def _percent_rank_cheap_high_sector_relative(
        cls,
        values: dict[str, float],
        sector_map: dict[str, str],
        is_foreign_private_issuer: dict[str, bool] | None = None,
    ) -> dict[str, float]:
        """Sector-relative counterpart to `_percent_rank_cheap_high` - same "lowest raw value ->
        highest percentile" convention, but each symbol is ranked ONLY against same-sector peers
        (`sector_map[symbol]`, GICS via company_profile.sector) instead of the full cross-sector
        universe. Symbols with no sector_map entry, or belonging to a sector with fewer than
        `_MIN_SECTOR_SLICE` members among `values`, are pooled into one residual group and ranked
        via the plain universe-wide `_percent_rank_cheap_high` instead - never dropped, never
        left unranked. Each group (per-sector and the residual pool) is winsorized via
        `_winsorize_group_values` before ranking - see that method's docstring for why.

        ADDED 2026-09-04 (real-money-readiness review, "always do what is best" directive - see
        this method's caller, `update_value_multiples_percentiles()`, for the full evidence
        trail and citations). Ties/single-sector/empty-input edge cases all delegate to
        `_percent_rank_cheap_high`'s own already-tested handling, per sector group.

        FPI PEER-GROUP SPLIT (added 2026-09-14) - same fix, same rationale, as
        `sector_neutral_zscore`'s own docstring in factor_normalization.py (this is Value's
        percentile-rank analog of that z-score primitive, and suffered the identical defect):
        a Foreign Private Issuer's P/E, P/B, P/S structurally run lower than US GICS-sector
        peers for country/currency-risk-discount reasons that have nothing to do with genuine
        relative cheapness - live-verified before this fix, FPIs were 44-52% of Value's own
        top-25 lists across every cap band despite being ~15-19% of the underlying universe.
        FPIs are pooled into one global cross-sector group (not dropped, not excluded from
        scoring) exactly as that z-score function's own FPI pool works.
        """
        fpi = is_foreign_private_issuer or {}
        groups: dict[str, list[str]] = {}
        residual: dict[str, float] = {}
        fpi_pool: dict[str, float] = {}
        for symbol, val in values.items():
            if fpi.get(symbol):
                fpi_pool[symbol] = val
                continue
            sector = sector_map.get(symbol)
            if sector is None:
                residual[symbol] = val
            else:
                groups.setdefault(sector, []).append(symbol)

        result: dict[str, float] = {}
        for symbols in groups.values():
            if len(symbols) < cls._MIN_SECTOR_SLICE:
                for symbol in symbols:
                    residual[symbol] = values[symbol]
                continue
            sector_values = {symbol: values[symbol] for symbol in symbols}
            result.update(cls._percent_rank_cheap_high(cls._winsorize_group_values(sector_values)))

        if fpi_pool:
            result.update(cls._percent_rank_cheap_high(cls._winsorize_group_values(fpi_pool)))
        if residual:
            result.update(cls._percent_rank_cheap_high(cls._winsorize_group_values(residual)))
        return result

    @staticmethod
    def _components_with_corrected_value(components_old: Any, value_score_new: float | None) -> str:
        """Return components (the Pass-1 JSON breakdown dict) re-serialized with its 'value'
        key set to value_score_new, every other pillar untouched.

        BUG FIX 2026-08-29 (goal-mode composite-score validation pass): update_value_multiples_
        percentiles()'s UPDATE previously wrote value_score/composite_score but never touched
        components - which still held the Pass-1 provisional (fixed-curve) value, not the
        corrected cross-sectional-percentile one this method's caller just computed. Live-
        audited: 4690/4708 scored symbols (99.6%) had components->'value' disagreeing with the
        real value_score column, by up to 94 points on a 0-100 scale. Not currently read by the
        scores API (lambda/api/routes/scores.py rebuilds its breakdown from the individual
        *_score columns directly), so this was a latent data-integrity bug, not a live user-
        facing one - fixed anyway since components is a real field in the API response model
        (lambda/api/models/responses.py) and a direct DB consumer would be misled.

        components_old comes back from psycopg2 already parsed to a dict for a real jsonb
        value; the str/None branches are defensive only (a symbol with no Pass-1 components at
        all shouldn't reach here, since value_score - required for this batch pass's own SELECT
        WHERE clause - is only ever set alongside components in Pass-1).
        """
        if isinstance(components_old, dict):
            components_new = dict(components_old)
        elif components_old:
            components_new = json.loads(components_old)
        else:
            components_new = {}
        components_new["value"] = value_score_new
        return json.dumps(components_new)

    def update_value_multiples_percentiles(self) -> None:
        """Batch pass: replace Pass-1's PROVISIONAL fixed-curve scores with a true
        cross-sectional percentile rank against the current run's universe, then FULLY
        RECOMPUTE value_score and composite_score from scratch off the raw stored inputs (not
        patched relative to whatever value_score/composite_score currently hold). Mirrors
        `update_rs_percentiles()`'s pure-overwrite pattern, not the additive-delta design this
        method used until the rewrite below - see "BUG FOUND + FIXED 2026-08-31" below.

        STALE-DOCSTRING NOTE (fixed 2026-09-16, factor-purity sweep, UPDATED same day after the
        MSCI z-score rebuild below): this top section and the MECHANISM paragraph below described
        a 5-input flat-20%-each construction (P/E/P/B/P/S/Forward-P/E/Dividend-Yield) that hasn't
        been true since 2026-09-15. The real, live construction is now MSCI's actual published
        Enhanced Value 3-leg z-score formula (P/B-or-P/CE, E/P, EV/CFO-or-P/CE, each 1/3 weight,
        no P/S or dividend-yield leg at all - universe-wide per-leg z-score, THEN a single
        sector-relative standardization of the equal-weighted composite, THEN +/-3 winsorization
        and a 0-100 conversion) - see the "MSCI ENHANCED VALUE Z-SCORE CONSTRUCTION" comment block
        further down in this same method for the actual, current logic and its primary-source
        citation. An earlier same-day pass (percentile-rank-per-leg, sector-relativized before
        combining) is itself now superseded - see that comment block's own "DROPPED from the
        prior construction" note for exactly what changed and why. Left the historical MECHANISM
        narrative below as-is (audit trail, not currently-accurate mechanism) rather than
        rewriting it, same "superseded, kept for history" convention this file uses elsewhere -
        trust the code/comments from "MSCI ENHANCED VALUE Z-SCORE CONSTRUCTION" onward, not this
        docstring's own top section or MECHANISM paragraph, for what's actually live.

        INVESTABILITY FLOOR ADDED 2026-09-13 (`vm.market_cap >= %s`, algo_config.min_market_
        cap_millions, same $300M threshold LiquidityChecks._check_market_cap() now enforces at
        trade entry): this percentile rank is computed against the CURRENT RUN'S UNIVERSE - if
        that universe includes thousands of sub-floor nanocaps, their more extreme P/E/P/B/P/S
        ratios distort the percentile boundaries real, investable companies get ranked against.
        Real index/factor methodology defines the eligible universe before computing exposures,
        never after - this makes the scoring population match that ordering instead of relying
        on a display-time filter to hide the effect. Sub-floor symbols simply aren't included
        in this pass and keep whatever Pass-1 (`_score_value`) already gave them.

        BUG FOUND + FIXED 2026-09-11 (goal: "value score rankings look wrong" investigation):
        this batch pass never selected/used `vm.pb_ratio_unavailable_reason`, so the
        negative-book-value P/B floor `_score_value` applies in Pass 1 (see
        test_stock_scores_pb_negative_book_value_floor_20260905.py) was silently undone every
        time this pass ran - since this pass unconditionally overwrites value_score for the
        whole universe on every post_run(), the floor never actually survived to the real
        stock_scores row. A distressed/negative-stockholders'-equity company's P/B component
        was dropped entirely instead of floored at 0.0, renormalizing its value_score over
        PE/PS/Forward-PE/Dividend only - inflating value_score for exactly the companies the
        floor exists to penalize. Same bug class as the PE `unprofitable_stock` / Forward P/E
        `negative_forward_eps` floors, which WERE already wired into this pass correctly - this
        one field was just missed when the negative-book-value floor was added 2026-09-05
        (after this pass's own PE/Forward-P/E floor wiring already existed). Fixed by selecting
        `vm.pb_ratio_unavailable_reason` and flooring `pb_pct[symbol] = 0.0` / appending
        `(0.0, 0.27)` to `components`, mirroring the PE/Forward-P/E treatment exactly.

        EXTENDED TO FORWARD P/E 2026-08-28 (see _score_value's "FORWARD P/E - ADDED 2026-08-28"
        docstring note): when Forward P/E was added to Value, it joined this percentile mechanism
        on the same logic that already applies to the other three multiples below, rather than
        being left on a fixed curve nothing has validated for this specific field. FCF yield,
        PEG, and Margin of Safety were all LATER removed from Value scoring entirely (same day,
        later passes - see _score_value's docstring "FCF YIELD - RESOLVED", "PEG - REMOVED FROM
        SCORING", and "MARGIN OF SAFETY - REMOVED FROM SCORING" notes) - none of the three
        appear in total_weight_old below anymore. PEG was never part of the percentile-rank
        mechanism even while it was still scored (not a multiple needing a peer-relative
        construction the way P/E/P/B/P/S/forward_pe do), so removing it only meant dropping it
        out of total_weight_old, same treatment FCF yield already got.

        UNPROFITABLE/NEGATIVE-FORECAST FLOOR ADDED 2026-08-28 (same-day, later pass - see
        _score_value's "UNPROFITABLE-COMPANY FLOOR ADDED 2026-08-28" / "UNPROFITABLE-FORECAST
        FLOOR ADDED 2026-08-28" docstring notes): P/E and Forward P/E previously EXCLUDED
        unprofitable/negative-forecast symbols from both the percentile universe and
        total_weight_old, same selection-bias bug class this method's own WHY section already
        flags for the PE-vs-PB/PS ranking dispute. Now: such symbols are identified via
        `pe_ratio_unavailable_reason == "unprofitable_stock"` /
        `forward_pe_unavailable_reason == "negative_forward_eps"`, floored at percentile 0.0
        (the worst - any negative earnings yield is worse than any non-negative one by
        definition), and DO count in total_weight_old at the normal 0.12/0.04 weight - matching
        _score_value's Pass-1 treatment exactly so the delta-reconciliation math stays internally
        consistent (both OLD and NEW are 0.0 for these symbols' PE/Forward-P/E term, so this
        correction pass contributes no further delta for them on that specific term - the
        definitive floor score was already assigned in Pass 1).

        WHY (goal 2026-08-28, "what does IBD/the best and brightest do - rethink this and do it
        that way"): every credible external methodology checked this session scores value/
        quality inputs via CROSS-SECTIONAL RANKING against a peer universe, never a fixed
        absolute threshold -
          - IBD: "All stocks are arranged in order of ... percentage change and assigned a
            percentile rank from 99 (highest) to 1 (lowest)" for EVERY SmartSelect rating
            (EPS Rank, RS Rating, SMR Rating) - https://ibdstock.com/ibd-stock-ratings-explained/
          - MSCI: "z-score: zi = (xi - mu) / sigma ... across the universe" for value/quality
            factors - https://www.msci.com/research-and-insights/blog-post/the-theory-of-value-relativity
        This file's OWN Momentum pillar already does this correctly (`update_rs_percentiles()`,
        below - a proven precedent this method mirrors) - Value's P/E/P/B/P/S never got the
        same treatment, still using hand-set thresholds (`_pe_curve_score`/`_pb_curve_score`/
        `_ps_curve_score`, e.g. "P/E<=10 -> one formula, <=20 -> another") that don't adapt to
        the market's actual valuation regime at any point in time - a well-documented weakness
        of absolute thresholds vs. relative ranking in exactly this context.

        VALIDATED, not just asserted (algo/research/value_absolute_curve_vs_relative_ranking_20260828.py,
        same complete-case Fama-MacBeth methodology as every other change this session):
        cross-sectional percentile beat the live fixed curve in EVERY era and spec tested -
        multivariate t: FULL 0.98->2.02, ERA1 -0.75->0.12, ERA2 2.48->3.06; univariate t: FULL
        2.06->3.29, ERA1 0.57->1.38, ERA2 2.55->3.48. A 5-year-own-history TIME-SERIES leg (the
        other half of MSCI's own recommended hybrid) was ALSO tested and did NOT help on this
        repo's actual data (t=-0.44 to -0.10, flat/negative) - not implemented, since the
        evidence for it specifically doesn't hold here even though the citation is real.

        MECHANISM: Pass 1 (`_score_value`, per-symbol, no access to the universe distribution)
        still calls `_pe_curve_score`/`_pb_curve_score` (the latter reused for Forward P/E too)
        as a PROVISIONAL placeholder so value_score/composite_score are never NULL mid-run -
        as of 2026-09-17 these return a flat NEUTRAL_PLACEHOLDER_SCORE (50.0), not a hand-set
        curve (see that constant's own docstring for the live-audit evidence the curve never
        survived as a real score anyway). `_ps_curve_score` was deleted 2026-09-16 as dead code
        once P/S was dropped from both passes entirely (see value_score.py's VALUE_MIN_WEIGHT
        docstring). This method runs
        after every symbol in this run has a value_score, computes the true cross-sectional
        percentile per ratio (independently - a symbol missing P/B still gets ranked on P/E and
        P/S), and FULLY RECOMPUTES value_score from the percentile scores of all five inputs -
        PE/PB/PS/Forward-P/E/Dividend-Yield are now ALL sector-relative percentile ranks (see
        "SECTOR-RELATIVE DIVIDEND YIELD" docstring note further down - dividend_yield was the
        last absolute-curve holdout until 2026-09-11), weighted exactly as `_score_value` itself
        weights them (20/20/20/20/20, per the UNIFORM EQUAL-WEIGHT note below). composite_score
        is then independently recomputed in full from quality_score/growth_score/risk_score/
        momentum_score (read as-is, untouched by this pass) plus the new value_score, via
        `BASE_PILLAR_WEIGHTS` - the same fixed weighting `_score_value`'s own caller uses,
        just re-derived here rather than patched.

        BUG FOUND + FIXED 2026-08-31 (goal session: "VCIG tops the scores and it's a shitty
        stock, dig in" - live-verified, this code is byte-identical to main, so this was live on
        production too, not a worktree artifact). The original design computed
        `value_score_NEW = value_score_OLD + delta`, reading `value_score_OLD` from the SAME
        mutable `stock_scores.value_score` column this method writes to - non-idempotent, since
        this batch pass runs unconditionally on the WHOLE universe on every single invocation of
        this loader's post_run(), regardless of `--symbols` scope (same bug class just found and
        fixed in `loaders/load_value_quality_growth_metrics.py`'s
        `update_quality_roe_roce_percentiles()` - see that method's own "BUG FOUND + FIXED
        2026-08-31" docstring note, which this fix mirrors exactly). Live-confirmed via two
        consecutive live calls today with zero underlying pe/pb/ps/forward_pe changes: TAP.A
        drifted 89.69 -> 83.70 -> 77.71 and CMCT drifted 81.84 -> 81.66 -> 81.48, the SAME delta
        applied twice on top of the prior call's already-corrected value instead of being
        computed fresh against a stable baseline - zero natural convergence, only the hard
        0/100 clamp eventually stops the drift (VCIG/BMA/CISS/AAPL/MSFT were already pinned at
        100.00/100.00/100.00/0.00/0.00 in this same test, consistent with the clamp already
        having been reached repeatedly in the normal pipeline cadence). This was the main
        mechanism - not just a one-time winsorization gap - behind multiple real, legitimate
        tickers (BMA, a large Argentine bank; CISS; TAP.A) clustering at or near the 0/100
        ceiling/floor on value_score well before any single pass's own math would justify it.
        Fixed by making this a pure function of the raw stored ratio/pillar columns, matching
        `update_rs_percentiles()`'s correct pattern - value_score and composite_score are now
        only ever WRITE targets here, never also read inputs, so running this any number of
        times with unchanged inputs produces the identical result every time.

        STALE NOTE, RESOLVED (originally: `_percent_rank_cheap_high` had no winsorization, so
        the single most extreme raw P/B or P/S always won percentile 100/0 regardless of whether
        that extremeness was genuine or a data artifact, e.g. VCIG's pb_ratio=0.01/ps_ratio=0.02).
        `_winsorize_group_values` (see `_percent_rank_cheap_high_sector_relative` below) now
        winsorizes each sector group at the 1st/99th percentile before ranking, matching MSCI's
        cited convention - kept here only so a future reader doesn't re-litigate an already-fixed
        gap (real-money-readiness audit, 2026-09-08).

        SECTOR-RELATIVE RANKING ADOPTED 2026-09-04 (real-money-readiness review, user directive
        "always do what is best, dig in and do the right best things around all of this",
        deciding the previously-open item tracked as
        algo/research/sector_relative_scoring_test_20260828.py / memory
        sector_relative_scoring_investigated_never_shipped_20260904). PE/PB/PS/Forward P/E are
        now percentile-ranked WITHIN each symbol's GICS sector (`company_profile.sector`, via
        `_percent_rank_cheap_high_sector_relative`) instead of against the full cross-sector
        universe - closing the gap that research script was built to test.

        PRIMARY-SOURCE CONFIRMATION 2026-09-16 (factor-purity sweep, user asked "what does the
        industry do?" directly): at adoption time this was justified ONLY by this repo's own
        Fama-MacBeth backtest (below) - an internal-evidence basis, the same category of
        adoption that got Momentum's sector-relative mom_12_1 and Risk's sector-neutral
        volatility REVERSED later after real MTUM/USMV N-PORT holdings crosschecks showed they
        hurt real-fund agreement (see momentum_scoring.py's "REVERSAL" history and
        risk_scoring.py's own volatility-universe-wide fix). Fetched and read MSCI's real,
        published Enhanced Value Indexes Methodology directly this session (msci.com/eqb,
        MSCI_Enhanced_Value_Index_Meth_Aug14.pdf, Appendix II "Value Z-Score Computation") to
        check whether Value's sector-relative choice was the same kind of unverified internal
        guess - it is NOT: MSCI's real construction is "compute each individual variable's
        z-score within the [universe-wide] Parent Index, [then] a sector relative score is then
        derived from the composite value z-score ... by standardizing the composite value
        z-score within each sector" - MSCI genuinely sector-relativizes Value, just at the
        COMPOSITE stage (after combining the 3 legs) rather than per-individual-variable (before
        combining) the way this method does it. This repo's sector-relative ADOPTION is
        therefore correct in kind, confirmed against the primary source, not merely an
        internally-validated guess like the two reversed pillars above - the remaining
        difference (per-variable vs. per-composite sector-relativization, and percentile rank
        vs. MSCI's winsorized-z-score-then-piecewise-transform) is a separate, still-open
        methodology-fidelity question, not a "was this the right call at all" one.

        WHY: cross-sectionally pooling all sectors before ranking P/E/P/B/P/S conflates genuine
        mispricing with persistent, structural sector-level valuation-regime differences (a
        Financial Services stock's P/E is mechanically lower than a Technology stock's for
        leverage/regulatory/growth-optionality reasons that have nothing to do with which one is
        actually cheap for what it is) - live-confirmed average P/E 19.0 (Financials) vs 32.4
        (Technology), average P/B 1.9 (Real Estate) vs 5.3 (Technology). Controlling for sector
        before ranking value multiples is standard quant-equity practice (Fama-French 1992
        already excludes financials from several factor constructions for exactly this reason;
        MSCI/Barra-style multi-factor models and AQR-style practitioner value composites
        routinely sector/industry-neutralize valuation ratios rather than rank them pooled
        market-wide) precisely to avoid a factor secretly becoming a sector bet.

        VALIDATED, not just asserted (re-ran algo/research/sector_relative_scoring_test_20260828.py
        fresh this session against real history, 111 usable months 2017-06 to 2026-08, n=6,474
        median monthly cross-section): sector-relative (`value_sector`) beat universe-wide
        (`value_uni`) in EVERY era, both specs -
          multivariate (5-pillar-controlled) t: FULL 2.54->2.94, ERA1 1.27->1.70, ERA2 2.25->2.40
          univariate t:                          FULL 4.62->4.91, ERA1 2.54->2.94, ERA2 3.96->3.97
        A 50/50 UNIVERSE/SECTOR blend (`value_blend`) was also tested and sits between the two on
        every spec except univariate ERA2 (where it edges out pure sector, 4.04 vs 3.97) - pure
        sector-relative is the more consistent winner on the more rigorous multivariate spec,
        so it was adopted outright rather than blended.

        Sector-sliced Spearman IC (within Financial Services/Real Estate only) came out slightly
        LOWER for `value_sector` than `value_uni` (FS 0.0754->0.0718, RE 0.0387->0.0261) - this
        is NOT a contradiction: within a single sector, sector-relative z-scoring is a monotonic
        transform of the same raw ordering universe-wide ranking already produces there (modulo
        winsorization-cutoff differences), so within-sector stock-picking power is roughly
        unchanged either way. The real gain sector-relative ranking captures is at the
        ACROSS-sector allocation level (which sector's stocks get called "cheap" at all) - only
        visible to the universe-wide multivariate/univariate tests above, not to a metric that
        holds sector fixed by construction.

        SECTOR SIZE CHECKED (small-sector noise risk, live-queried this session against the
        actual scored universe, not company_profile's full historical roster): smallest scored
        sector is Consumer Defensive at 117 symbols, next Communication Services 130 - all far
        above `_MIN_SECTOR_SLICE` (20) and standard percentile-stability rule-of-thumb minimums
        (30-50). `_percent_rank_cheap_high_sector_relative` still floors any thin/unmapped group
        into a universe-wide-ranked residual pool defensively, but this floor is not expected to
        bind materially in normal operation.

        TRADEOFF, acknowledged not ignored: a pure sector-relative composite can in principle
        rank an expensive-for-its-sector Tech stock above a cheap-for-its-sector Financials
        stock even where the Financials stock is cheaper in absolute terms - by design, this
        pillar is choosing to treat persistent sector-level multiple differences as a regime
        effect to control for, not information to keep. That is the standard quant-equity
        position (see citations above), and this session's own re-test confirms it wins here,
        but it is a real, deliberate choice, not a free lunch.

        ACTIVATION: restart-only, not backfill - this is a `loaders/load_stock_scores.py` batch
        pass (`update_value_multiples_percentiles`, part of `post_run()`), not `_score_*` reason
        logic served directly by the API. It takes effect the next time the stock_scores loader
        actually runs (via the pipeline scheduler - never invoke it standalone) and rewrites
        value_score/composite_score for the whole scored universe; `lambda/api/dev_server.py`
        reads whatever is currently in `stock_scores` and needs no code change, but per this
        repo's own no-hot-reload pattern, restart it anyway if it's been holding a stale
        in-memory reference to anything in this module.

        CRITICAL: raises on failure, same as `update_rs_percentiles()` - an inconsistent value_
        score/composite_score is a live-trading-relevant correctness issue, not just Phase 7
        display noise.
        """
        try:
            with _owner().DatabaseContext("write") as cur:
                # ACTIVE-UNIVERSE GUARD (added 2026-09-09, migration 1276's own code fix - see
                # NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE's own module-level comment in
                # utils/loaders/helpers.py for the full evidence trail). Without this, a closed-
                # end fund/BDC/trust row that predates (or later drifted out of) the active-
                # universe exclusion get_active_symbols(exclude_etfs=True) enforces for the
                # per-symbol fetch path keeps getting value_score/composite_score freshly
                # recomputed here forever - the per-symbol fetch that WOULD exclude it going
                # forward never runs an UPDATE/DELETE against a row it no longer selects.
                cur.execute(
                    """
                    SELECT ss.symbol, ss.value_score, ss.composite_score, ss.risk_score,
                           ss.quality_score, ss.growth_score, ss.momentum_score,
                           vm.pe_ratio, vm.pb_ratio, vm.ps_ratio, vm.forward_pe,
                           vm.dividend_yield, vm.fcf_yield,
                           vm.pe_ratio_unavailable_reason, vm.forward_pe_unavailable_reason,
                           vm.pb_ratio_unavailable_reason,
                           ss.components, cp.sector, ss.data_completeness, ss.data_unavailable,
                           ss.unavailable_metrics, vm.ps_ratio_unavailable_reason,
                           COALESCE(cis.is_foreign_private_issuer, false),
                           vm.enterprise_value, qm.operating_cash_flow, cp.industry, vm.market_cap
                    FROM stock_scores ss
                    JOIN value_metrics vm ON vm.symbol = ss.symbol
                    LEFT JOIN company_profile cp ON cp.symbol = ss.symbol
                    JOIN stock_symbols su ON su.symbol = ss.symbol
                    LEFT JOIN company_info_sec cis ON cis.symbol = ss.symbol
                    LEFT JOIN quality_metrics qm ON qm.symbol = ss.symbol
                    """
                    + LIQUIDITY_FLOOR_JOIN_SQL
                    + """
                    WHERE ss.value_score IS NOT NULL
                      AND COALESCE(vm.data_unavailable, false) = false
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
                    "[STOCK_SCORES] update_value_multiples_percentiles: no eligible rows found "
                    "(value_score IS NOT NULL joined to value_metrics) - skipping, nothing to correct."
                )
                return

            # book_to_price_raw: MSCI z-scores the INVERSE of Price/Book (Appendix II: "the mean
            # and standard deviation of the inverse of the corresponding variable") so that a
            # higher value consistently means "cheaper" across all 3 legs, matching earnings_
            # yield_raw/cash_yield_raw_map's own already-inverted (E/P, CFO/EV) convention -
            # stored as book-to-price here, not raw pb_ratio, for that reason.
            book_to_price_raw: dict[str, float] = {}
            # cash_yield_raw_map: MSCI Enhanced Value's real third leg is Enterprise
            # Value-to-Cash-Flow-from-Operations (EV/CFO), not a price/equity-basis metric -
            # confirmed against MSCI's own published fact sheet for the real MSCI USA Enhanced
            # Value Index / VLUE holdings methodology (ishares.com/us/products/251616). Prefer
            # operating_cash_flow (quality_metrics.operating_cash_flow, CFO before capex, the
            # actual MSCI-stated numerator) / enterprise_value (value_metrics.enterprise_value)
            # when both are available and enterprise_value > 0 - this is leverage-aware, unlike
            # a price-basis yield, which matters a lot for anything with meaningful net debt
            # (live-confirmed root cause of the value_score-vs-real-VLUE near-zero correlation,
            # rho=-0.063/p=0.464: JPM scored 19.09 despite normal P/E 14.85/fwd-P/E 14.01 purely
            # because fcf_yield=-15.57% - a bank's loan-issuance-driven OCF sign flip, not real
            # cheapness/expensiveness - and F/GM's fcf_yield/PRICE ~21% looked extreme-cheap
            # while their EV/market_cap ratio is ~3.6x/2.3x on debt-heavy auto-financing arms,
            # which a price-basis yield can't see at all). Falls back to the old fcf_yield
            # (FCF/market_cap) proxy when operating_cash_flow or enterprise_value is missing -
            # same graceful-degradation shape as every other leg's *_reason fallback in this
            # file, not a full replacement, since this schema doesn't guarantee CFO/EV coverage
            # matches fcf_yield's.
            cash_yield_raw_map: dict[str, float] = {}
            # earnings_yield_raw: forward P/E when available, else trailing P/E (MSCI's own
            # stated substitution rule for a missing Fwd P/E - see note below).
            earnings_yield_raw: dict[str, float] = {}
            # unprofitable_symbols/negative_fwd_symbols: floored at percentile 0.0 directly
            # below (not run through _percent_rank_cheap_high) - see _score_value's
            # "UNPROFITABLE-COMPANY FLOOR ADDED 2026-08-28" docstring note for why a floor
            # (not exclusion) is the theoretically correct treatment here.
            unprofitable_symbols: set[str] = set()
            negative_fwd_symbols: set[str] = set()
            negative_book_value_symbols: set[str] = set()
            sector_map: dict[str, str] = {}
            is_fpi: dict[str, bool] = {}
            market_caps: dict[str, float] = {}
            for row in rows:
                symbol, pe, pb, fwd_pe = row[0], row[7], row[8], row[10]
                fcf_yield_raw = safe_float(row[12], f"{symbol}.fcf_yield") if row[12] is not None else None
                enterprise_value_raw = row[23] if len(row) > 23 else None
                operating_cash_flow_raw = row[24] if len(row) > 24 else None
                industry_raw = row[25] if len(row) > 25 else None
                # market_cap RE-ADDED 2026-09-17 (MSCI-reversion pass): a 2026-09-17 dead-code
                # sweep had removed this SELECT column/dict as write-only, correct at the time -
                # but factor_normalization.py's universe_wide_zscore now accepts an optional
                # `market_caps` weighting dict (MSCI's real z-score formula weights by free-float
                # market cap, not equal-weighted), so this is a genuine consumer again, not a
                # repeat of the same dead-weight mistake.
                market_cap_raw = row[26] if len(row) > 26 else None
                if market_cap_raw is not None:
                    market_caps[symbol] = float(market_cap_raw)
                pe_reason, fwd_pe_reason, pb_reason = row[13], row[14], row[15]
                sector = apply_mortgage_reit_sector_override(symbol, row[17])
                if sector is not None:
                    sector_map[symbol] = sector
                # GICS FINANCIALS SECTOR-WIDE EV/CFO OMISSION (2026-09-16, factor-purity sweep
                # - fetched and read MSCI_Enhanced_Value_Index_Meth_Aug14.pdf directly this
                # session, Appendix II "Value Z-Score Computation"). MSCI's real, published rule
                # is stated purely in terms of GICS SECTOR, not a narrower industry list: "Fwd
                # P/E, P/B for all securities in the GICS Financials Sector" (Cases 4-6) - the
                # EV/CFO-or-P/CE leg is dropped entirely for the WHOLE Financials sector (GICS
                # code 40), reweighting the remaining two legs to 50/50, not just for the
                # narrower DEPOSITORY_BANK_INDUSTRIES/INSURANCE_UNDERWRITER_INDUSTRIES subset
                # this file previously carved out (added 2026-09-15, "BANK/INSURER EXCLUSION"
                # note below, kept for its still-valid JPM/OCF-sign-flip evidence of WHY the leg
                # is nonsense for banks specifically - just too narrow a trigger). Under the old
                # trigger, an asset manager, broker-dealer, or fintech classified "Financial
                # Services" but not a depository bank or insurance underwriter would still get
                # scored on EV/CFO (or the fcf_yield fallback) - a leg MSCI's real methodology
                # never gives it. `components`'s existing total_weight renormalization already
                # produces the correct MSCI 50/50 split automatically once a leg is omitted (2
                # components at 1/3 each, total_weight=2/3, divide-through -> effective 50/50) -
                # no separate reweighting logic needed, only the trigger condition changes.
                is_cfo_nonsense_industry = sector == "Financial Services" or (
                    industry_raw in DEPOSITORY_BANK_INDUSTRIES or industry_raw in INSURANCE_UNDERWRITER_INDUSTRIES
                )
                # FPI peer-group split (2026-09-14, goal-session "fix z-scoring issues"
                # directive - see sector_neutral_zscore's own docstring in
                # factor_normalization.py). row[22] is
                # COALESCE(cis.is_foreign_private_issuer, false) per this query's SELECT above.
                if len(row) > 22:
                    is_fpi[symbol] = bool(row[22])
                if pe_reason == "unprofitable_stock":
                    unprofitable_symbols.add(symbol)
                if pb is not None and float(pb) > 0:
                    book_to_price_raw[symbol] = 1.0 / float(pb)
                elif pb_reason == "negative_book_value":
                    negative_book_value_symbols.add(symbol)
                if fwd_pe_reason == "negative_forward_eps":
                    negative_fwd_symbols.add(symbol)
                # BUG FIXED 2026-09-17 (factor-purity dig, live-caught by comparing this code
                # against its OWN neighboring "already-inverted (E/P...)" comment on
                # book_to_price_raw above - they disagreed). This used to store the raw P/E
                # multiple itself (fwd_pe/pe, e.g. 25.0 for a $25-per-$1-earnings stock)
                # directly into earnings_yield_raw with no inversion - unlike book_to_price_raw
                # three lines above, which correctly computes 1.0/pb. z-scoring an un-inverted
                # P/E and averaging it into the same composite as the correctly-inverted
                # book-to-price/cash-yield legs rewarded a HIGH P/E (expensive/glamour) stock
                # with a HIGH earnings-leg z-score - backwards for a leg whose whole job is
                # "higher = cheaper = better". No existing test caught this: every test in
                # tests/unit/test_value_multiples_percentile_ranking_20260828.py holds forward_pe
                # IDENTICAL between compared symbols and varies book/cash-yield instead, so the
                # P/E leg's own direction was never actually asserted. Inverted to match MSCI's
                # real Earnings/Price ("Fwd E/P") descriptor and book_to_price_raw's own
                # convention.
                if fwd_pe is not None and float(fwd_pe) > 0:
                    earnings_yield_raw[symbol] = 1.0 / float(fwd_pe)
                elif pe is not None and float(pe) > 0:
                    earnings_yield_raw[symbol] = 1.0 / float(pe)
                # FINANCIALS-SECTOR-WIDE EXCLUSION (originally added 2026-09-15 as a narrower
                # bank/insurer-industry-only carve-out; BROADENED 2026-09-16 to the whole GICS
                # Financials sector - see `is_cfo_nonsense_industry`'s own comment above for the
                # MSCI Appendix II citation). Both EV/CFO and the FCF/market_cap fallback are
                # nonsense for depository banks/risk-bearing insurers specifically - operating_
                # cash_flow for these industries is dominated by loan origination/deposit flows
                # or reserve movements under GAAP, not a "cash generation" measure comparable to
                # an operating company's (live-confirmed: JPM operating_cash_flow=-$147.8B
                # despite being a normal, healthy bank), and enterprise_value is equally
                # meaningless when "debt" includes customer deposits, not leverage - this
                # evidence is why MSCI's own real rule drops the leg for the sector, not just
                # this codebase's earlier narrower guess at which industries within it are
                # "nonsense enough" to matter. Leg omitted entirely for the whole sector - same
                # "floored/no entry, other legs renormalize" pattern as unprofitable_symbols/
                # negative_book_value_symbols above - rather than scored on a number that isn't
                # measuring what the leg claims to measure.
                if is_cfo_nonsense_industry:
                    pass
                else:
                    ev = float(enterprise_value_raw) if enterprise_value_raw is not None else None
                    cfo = float(operating_cash_flow_raw) if operating_cash_flow_raw is not None else None
                    if ev is not None and ev > 0 and cfo is not None:
                        cash_yield_raw_map[symbol] = cfo / ev
                    elif fcf_yield_raw is not None:
                        # Fallback: EV/CFO inputs missing for this symbol - use the old
                        # price-basis fcf_yield proxy rather than dropping the leg entirely.
                        cash_yield_raw_map[symbol] = float(fcf_yield_raw)

            # MSCI ENHANCED VALUE Z-SCORE CONSTRUCTION (REBUILT 2026-09-16, factor-purity sweep -
            # user asked directly "what does the industry do? we want to do like the industry").
            # Fetched and read MSCI_Enhanced_Value_Index_Meth_Aug14.pdf's actual Appendix II
            # ("Value Z-Score Computation") this session - not recalled/paraphrased - and rebuilt
            # this method to match it exactly, replacing the prior per-leg SECTOR-RELATIVE
            # PERCENTILE-RANK construction (adopted 2026-09-04 on this repo's own backtest
            # evidence alone - see "SECTOR-RELATIVE RANKING ADOPTED"/"PRIMARY-SOURCE
            # CONFIRMATION" docstring notes above: that adoption's DIRECTION was right - MSCI
            # really does sector-relativize Value - but its MECHANICS were not quite MSCI's
            # real ones). MSCI's real 3-step construction:
            #   1. z-score EACH leg UNIVERSE-WIDE (within the whole eligible universe, "the MSCI
            #      Parent Index" - NOT per-sector, NOT size-neutralized - see universe_wide_zscore
            #      below), on the INVERSE of each ratio (book_to_price_raw above).
            #   2. composite = equal-weighted average of the available leg z-scores (1/3 each, or
            #      1/2 each for the two legs GICS Financials-sector names get - see the
            #      Financials-sector-wide EV/CFO omission above, Appendix II Cases 4-6).
            #   3. Re-standardize the COMPOSITE universe-wide (not each leg individually, and
            #      only once), then winsorize the result at +/-3 - MSCI's own explicitly stated
            #      output bound.
            # STEP 3 SECTOR RELATIVIZATION REMOVED 2026-09-17 (goal session: "we are not trying
            # to create indices, we are trying to measure the factor itself... ranked based on
            # most representative of that factor"). This step used to sector-relativize the
            # composite (`sector_neutral_zscore`) per MSCI's real Enhanced Value formula - not
            # wrong as a citation (VLUE, the real iShares MSCI USA Value Factor ETF, genuinely
            # tracks a sector-relative index, live-verified via web search this session), but a
            # category error: MSCI's sector step controls tracking error against their cap-
            # weighted parent index for a licensable ETF product - a portfolio-construction
            # constraint, not a factor-measurement one. This repo's goal is to measure the Value
            # factor itself, which is exactly what Fama-MacBeth cross-sectional regression (Fama
            # & MacBeth 1973) - the academic standard this repo's OWN validation scripts
            # (fama_macbeth_value_factors.py et al.) already use for every factor test - does
            # without any sector step. Same fix, same reasoning, applied identically to Quality
            # the same session (vqg_quality_batch.py's update_quality_sector_neutral_scores) -
            # Quality and Value were the last two pillars still sector-relativizing their
            # composite after Growth/Momentum/Risk had already converged on universe-wide (for a
            # different reason - a live MTUM/USMV holdings crosscheck). Now uses
            # `universe_wide_zscore`, the same primitive those three already use for their own
            # final step - `sector_map`/`is_fpi` built above are no longer consumed by this step
            # (kept, still harmlessly computed - see this file's own "leave the SELECT as-is"
            # precedent elsewhere rather than risk a row-index reshuffle for a pure dead-code
            # trim).
            # DROPPED from the prior construction to match MSCI exactly: per-leg sector-relative
            # ranking (relativizing each leg separately and then averaging is NOT the same
            # computation as averaging first and relativizing once, even though both are
            # "sector-aware") and Barra-style size-neutralization on the cash-yield leg (added
            # 2026-09-15 on real evidence that residual size effects leak into cash/dividend
            # yields - a genuine, validated enhancement, but not part of MSCI's literal published
            # formula, and this session's directive is explicitly to match the industry's actual
            # construction, not to keep every independently-defensible enhancement layered on
            # top of it).
            #
            # Final 0-100 conversion uses zscore_to_percentile_scale (the same normal-CDF
            # transform already used to bound every other z-score-based pillar in this codebase -
            # Quality, Growth, Risk, Momentum - to [0,100]), NOT MSCI's own "Final Value Score"
            # piecewise transform (1+Z / (1-Z)^-1, Section 2.2.3): that transform is a
            # PORTFOLIO-WEIGHTING construction specific to MSCI's own index (an unbounded-above
            # multiplier applied to market-cap weight, not a rating comparable to this system's
            # other 0-100 pillar scores) and is already used verbatim, in its correct domain, by
            # market_cap_tilt.py's *_tilted_weight columns - this method produces a RATING, that
            # one produces a PORTFOLIO WEIGHT, and each uses the MSCI transform appropriate to
            # its own job rather than reusing one formula for both.
            leg_book_to_price_z = universe_wide_zscore(book_to_price_raw, market_caps)
            leg_earnings_z = universe_wide_zscore(earnings_yield_raw, market_caps)
            leg_cash_z = universe_wide_zscore(cash_yield_raw_map, market_caps)
            # NEGATIVE-BOOK-VALUE DISTRESS FLOOR TAKES PRIORITY OVER THE CASH-YIELD SUBSTITUTE
            # (established 2026-09-15, live-verified value-trap gap: BHC/BMBL/EMBC scoring
            # value_score 99.9+ despite negative stockholders' equity, ROE -13 to -85 - a
            # distressed, heavily levered company's tiny market cap mechanically inflates its
            # cash yield into a huge "cheap" number, e.g. BHC fcf_yield=35.8%, EMBC=49.4%). MSCI's
            # stated "missing P/B -> P/CE" substitution rule is for genuinely MISSING data, not
            # for a real, known, definitionally-worst signal (negative equity) - so this floor is
            # applied here, at the leg-z level, using MSCI's own -3 winsorization bound as the
            # natural "worst" sentinel (consistent with how every other floor in this file uses
            # the scale's own worst value rather than an arbitrary number).
            for symbol in negative_book_value_symbols:
                leg_book_to_price_z[symbol] = -3.0
            # Both earnings measures unusable (unprofitable trailing AND negative forward
            # estimate) - genuinely the worst possible Earnings/Price outcome floor.
            for symbol in unprofitable_symbols & negative_fwd_symbols:
                leg_earnings_z[symbol] = -3.0

            # MSCI 3-LEG VALUE COMPOSITE RESTORED 2026-09-17 (reverts the same-day AQR
            # single-measure pivot documented in git history at commit 4beaf7f1c - explicit
            # user decision after a fresh audit compared this file's live code against MSCI's
            # actual published Enhanced Value Index Methodology and found the AQR pivot had
            # silently replaced it; user chose MSCI fidelity over AQR-purism for Value/
            # Momentum/Quality, see pillar_weights.py's governance-comment block for the full
            # record). Equal-thirds blend of Book/Price, Fwd-Earnings/Price, and Cash-
            # Earnings/Price (EV/CFO or its fcf_yield fallback), with MSCI's own stated
            # substitution rule (missing P/B -> Cash-Earnings/Price leg) and the
            # GICS-Financials-sector 2-leg reweighting (EV/CFO leg dropped sector-wide, see
            # `is_cfo_nonsense_industry` above) - restored verbatim from the pre-AQR
            # implementation, not reconstructed from scratch.
            composite_z_by_symbol: dict[str, float] = {}
            weight_by_symbol: dict[str, float] = {}
            for row in rows:
                symbol = row[0]
                pb, pb_reason = row[8], row[15]
                # BUG FOUND + FIXED 2026-09-15 (algo-fd/algo-f5): a P/B-missing symbol must not
                # get cash_yield counted TWICE - once as the MSCI-stated substitute for the
                # missing Book/Price leg, once again as its own independent Cash-Earnings/Price
                # leg - that would give cash-flow signal 2/3 nominal weight instead of the
                # intended equal thirds. pb_used_cash_substitute tracks whether this symbol
                # already consumed the cash leg as the P/B substitute, so the independent leg
                # below is skipped for it.
                pb_used_cash_substitute = False
                legs: list[tuple[float, float]] = []
                if symbol in leg_book_to_price_z and pb is not None and float(pb) > 0:
                    legs.append((leg_book_to_price_z[symbol], 1.0 / 3.0))
                elif pb_reason == "negative_book_value" and symbol in leg_book_to_price_z:
                    legs.append((leg_book_to_price_z[symbol], 1.0 / 3.0))
                elif symbol in leg_cash_z:
                    # MSCI's own stated substitution: missing P/B -> cash earnings (P/CE) leg.
                    # Only reached for genuinely missing (not negative/distressed) book value.
                    legs.append((leg_cash_z[symbol], 1.0 / 3.0))
                    pb_used_cash_substitute = True
                if symbol in leg_earnings_z:
                    legs.append((leg_earnings_z[symbol], 1.0 / 3.0))
                if symbol in leg_cash_z and not pb_used_cash_substitute:
                    legs.append((leg_cash_z[symbol], 1.0 / 3.0))
                total_weight = sum(w for _, w in legs)
                if total_weight <= 0:
                    continue
                weight_by_symbol[symbol] = total_weight
                composite_z_by_symbol[symbol] = sum(v * w for v, w in legs) / total_weight

            # STEP 3 (2026-09-17, "measure the factor itself" directive - see this method's own
            # "MSCI ENHANCED VALUE Z-SCORE CONSTRUCTION" comment block, updated below): re-
            # standardize the COMPOSITE universe-wide, not per-sector - MSCI's sector-relative
            # composite step exists to control tracking error against their cap-weighted parent
            # index for a licensable ETF product, a portfolio-construction constraint, not a
            # factor-measurement one. Winsorize at +/-3 is kept (a real published normalization
            # tail treatment, not MSCI-index-specific).
            universe_z = universe_wide_zscore(composite_z_by_symbol, market_caps)
            universe_z = {symbol: max(-3.0, min(3.0, z)) for symbol, z in universe_z.items()}
            value_pct = zscore_to_percentile_scale(universe_z)

            logger.info(
                f"[STOCK_SCORES] Value multiples MSCI z-score universe (universe-wide "
                f"composite): "
                f"Book/Price {len(leg_book_to_price_z)} "
                f"({len(negative_book_value_symbols)} floored negative-book-value), "
                f"Earnings/Price {len(leg_earnings_z)}, Cash-Earnings/Price {len(leg_cash_z)}, "
                f"composite scored {len(composite_z_by_symbol)}"
            )

            # Same configurable completeness gate load_stock_scores.py's Pass 1 uses (default
            # 70.0) - needed below so a value_score this pass withholds is reflected in
            # data_completeness/data_unavailable too, not just left at Pass 1's stale (higher)
            # reading (2026-09-07 real-money-readiness audit).
            min_completeness_threshold = getattr(self, "_min_completeness_threshold", 70.0)

            updates: list[tuple[str, float | None, float, str | None, float, bool, str, str | None]] = []
            for row in rows:
                symbol, value_score_old, composite_score_old, risk_score = row[0], row[1], row[2], row[3]
                quality_score, growth_score, momentum_score = row[4], row[5], row[6]
                components_old = row[16]
                data_completeness_old = float(row[18]) if row[18] is not None else None
                data_unavailable_old = bool(row[19]) if row[19] is not None else False
                unavailable_metrics_old: dict[str, str] = dict(row[20]) if row[20] else {}
                value_score_old = float(value_score_old)
                composite_score_old = float(composite_score_old)

                # Legs already combined into a per-sector-relativized composite z-score (and
                # converted to 0-100) in the pass above - see this method's own "MSCI ENHANCED
                # VALUE Z-SCORE CONSTRUCTION" comment block for the full 3-step formula and its
                # primary-source citation. `weight_by_symbol` is the same nominal per-leg weight
                # sum the VALUE_MIN_WEIGHT gate below needs (1/3 per leg, 1/2 for a
                # Financials-sector symbol's 2 legs).
                total_weight = weight_by_symbol.get(symbol, 0.0)
                if total_weight <= 0:
                    # Defensive only - can't happen if value_score is a real float (it required
                    # total_weight > 0 to compute in the first place), but never divide by zero.
                    continue

                # VALUE_MIN_WEIGHT gate (2026-09-07 real-money-readiness audit): this pass fully
                # recomputes value_score every run but never re-applied _score_value's own
                # VALUE_MIN_WEIGHT gate (loaders/stock_scores/value_score.py) - so a symbol that
                # cleared Pass 1 off a thicker component set, but loses components by the time
                # THIS batch pass runs (e.g. PE excluded by _pe_earnings_too_volatile with no PB
                # available), could end up with total_weight as low as 0.27 - a single multiple -
                # and that one raw (winsorized) percentile became the entire value_score
                # verbatim. Live-confirmed RILY
                # (B. Riley Financial): PE excluded, PB missing, only PS available (ratio 0.22) -
                # value_score=97.61, #1 in the whole 5,047-symbol universe off a single metric
                # with no PE/PB cross-check. Same "insufficient data, don't fabricate a score"
                # treatment as Pass 1 (see test_value_score_min_weight_gate_percentile_pass_
                # 20260907.py).
                if total_weight < VALUE_MIN_WEIGHT:
                    logger.warning(
                        f"[STOCK_SCORES] {symbol} value_score withheld in percentile pass: only "
                        f"{total_weight:.2f}/1.00 nominal weight available, below "
                        f"VALUE_MIN_WEIGHT={VALUE_MIN_WEIGHT}."
                    )
                    value_score_new = None
                else:
                    value_score_new = round(max(0.0, min(100.0, value_pct[symbol])), 2)

                # Pure recompute of composite_score from the 5 pillar scores as they currently
                # stand in stock_scores (quality/growth/risk/momentum are untouched by this
                # pass - only value_score changed above), mirroring _score_value's own caller
                # (no weight redistribution for a missing pillar - GOVERNANCE rule, same as
                # Pass 1) instead of patching composite_score_old by a delta.
                # GROWTH RESTORED TO COMPOSITE 2026-09-17 (same-day reversal - see
                # pillar_weights.py's BASE_PILLAR_WEIGHTS "ABOVE DECISION SUPERSEDED" note).
                weights = BASE_PILLAR_WEIGHTS
                composite_val = 0.0
                for pillar_name, pillar_score in (
                    ("quality", quality_score),
                    ("value", value_score_new),
                    ("risk", risk_score),
                    ("momentum", momentum_score),
                    ("growth", growth_score),
                ):
                    if pillar_score is not None:
                        composite_val += float(pillar_score) * weights[pillar_name]
                composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)

                # data_completeness/data_unavailable resync (2026-09-07, same audit as the
                # VALUE_MIN_WEIGHT gate above): nulling value_score here without also updating
                # these two columns would leave a stale (too-high) data_completeness and
                # data_unavailable=False from Pass 1 sitting next to a now-NULL value_score - the
                # exact inconsistency Pass 1's own "CRITICAL FIX...Enforce completeness
                # threshold" block (load_stock_scores.py) exists to prevent, just reintroduced by
                # this second write path. Mirrors that same available_weight-of-BASE_PILLAR_
                # WEIGHTS formula exactly (quality/growth/value/risk/momentum).
                all_scores_new: dict[str, float | None] = {
                    "quality": float(quality_score) if quality_score is not None else None,
                    "value": value_score_new,
                    "risk": float(risk_score) if risk_score is not None else None,
                    "momentum": float(momentum_score) if momentum_score is not None else None,
                    "growth": float(growth_score) if growth_score is not None else None,
                }
                available_weight = sum(
                    BASE_PILLAR_WEIGHTS[pillar] for pillar, score in all_scores_new.items() if score is not None
                )
                data_completeness_new = min(99.99, round(available_weight * 100, 2))
                data_unavailable_new = data_completeness_new < min_completeness_threshold

                # unavailable_metrics/reason resync (2026-09-08, live-found via LTGO: DB row had
                # value_score=NULL but unavailable_metrics only listed
                # growth/risk/momentum, and reason still read the stale higher completeness
                # from before this pass withheld value_score - same inconsistency class the
                # data_completeness/data_unavailable fix above closed, just missed for these two
                # sibling fields - a coverage/debugging consumer reading `reason` or
                # `unavailable_metrics` off this row undercounts "value" as a missing factor and
                # misstates the real completeness %.
                unavailable_metrics_new = dict(unavailable_metrics_old)
                if value_score_new is None:
                    unavailable_metrics_new["value"] = "value_min_weight_gate_below_threshold"
                else:
                    unavailable_metrics_new.pop("value", None)
                if data_unavailable_new:
                    reason_new = (
                        f"Completeness {data_completeness_new:.2f}% < {min_completeness_threshold}% "
                        f"threshold (missing metrics: {', '.join(sorted(unavailable_metrics_new.keys()))})"
                    )
                else:
                    reason_new = None

                if (
                    value_score_new != value_score_old
                    or composite_score_new != composite_score_old
                    or data_completeness_new != data_completeness_old
                    or data_unavailable_new != data_unavailable_old
                    or unavailable_metrics_new != unavailable_metrics_old
                ):
                    # BUG FIX 2026-08-29 (goal-mode composite-score validation pass): components
                    # must be kept in sync with the corrected value_score here, or it silently
                    # drifts from the real composite_score math - see
                    # _components_with_corrected_value's own docstring for the full evidence.
                    components_json = self._components_with_corrected_value(components_old, value_score_new)
                    updates.append(
                        (
                            symbol,
                            value_score_new,
                            composite_score_new,
                            components_json,
                            data_completeness_new,
                            data_unavailable_new,
                            json.dumps(unavailable_metrics_new),
                            reason_new,
                        )
                    )

            updates.extend(self._withhold_value_below_floor())

            if not updates:
                logger.info(
                    "[STOCK_SCORES] Value multiples percentile pass: no symbol's value_score/"
                    "composite_score changed (expected on a repeat run with unchanged inputs - "
                    "this pass is now idempotent, see its 'BUG FOUND + FIXED 2026-08-31' note)."
                )
                return

            with _owner().DatabaseContext("write") as cur:
                # ::numeric/::boolean casts (added 2026-09-17, factor-purity follow-up - see
                # risk_scoring.py's identical fix, applied here for the same reason and same
                # live-confirmed effect): this UPDATE mixes real floats (corrected symbols) with
                # None (withheld, via `_withhold_value_below_floor()`) in the same value_score
                # column position - the same mixed-None/float psycopg2 wrong-inferred-
                # column-type gotcha already fixed for quality_score/momentum_score when THEIR
                # OWN withhold passes were added, never ported here despite this method's own
                # `_withhold_value_below_floor()` landing 2026-09-16. Uncast, this raised
                # psycopg2.errors.DatatypeMismatch on every real run, and because post_run()
                # calls this method unguarded, the exception aborted every pass after it too
                # (update_growth_sector_neutral_scores/update_momentum_sector_relative_mom_12_1/
                # update_market_cap_tilted_weights) - not just leaving value_score stale.
                _owner().execute_values(
                    cur,
                    """
                    UPDATE stock_scores AS ss
                    SET value_score = v.value_score::numeric,
                        composite_score = v.composite_score::numeric,
                        components = v.components::jsonb,
                        data_completeness = v.data_completeness::numeric,
                        data_unavailable = v.data_unavailable::boolean,
                        unavailable_metrics = v.unavailable_metrics::jsonb,
                        reason = v.reason,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (VALUES %s) AS v(symbol, value_score, composite_score, components,
                                           data_completeness, data_unavailable,
                                           unavailable_metrics, reason)
                    WHERE ss.symbol = v.symbol
                    """,
                    updates,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s)",
                )
            logger.info(
                f"[STOCK_SCORES] Value multiples cross-sectional percentile pass corrected "
                f"{len(updates)}/{len(rows)} symbols' value_score/composite_score (post_run completed)"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"Value multiples percentile batch update failed - stock scores cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _withhold_value_below_floor(
        self,
    ) -> list[tuple[str, float | None, float, str | None, float, bool, str, str | None]]:
        """Companion to update_value_multiples_percentiles(): finds the COMPLEMENT of that
        method's own correction population - symbols with a real value_score but ineligible for
        correction (below the liquidity floor, or excluded by
        NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE) - and withholds value_score (NULL) plus
        recomputes composite_score/data_completeness/data_unavailable/unavailable_metrics/reason
        to match, rather than leaving Pass 1's stale, potentially-floored curve value in place
        indefinitely.

        PORTED 2026-09-16 (factor-purity sweep - this exact bug class was already found and
        fixed for Quality (vqg_quality_batch.py's `_withhold_quality_below_floor`) and Momentum
        (momentum_scoring.py's `_withhold_momentum_below_floor`, commit c1a3dd899) but never
        ported here or to Growth/Risk - see those two methods' own docstrings for the shared
        rationale. Same gap, same fix, same shape.

        Returns tuples in the same (symbol, value_score, composite_score, components,
        data_completeness, data_unavailable, unavailable_metrics, reason) shape
        update_value_multiples_percentiles()'s own `updates` list uses, so the caller can extend
        one batch UPDATE with both.
        """
        with _owner().DatabaseContext("write") as cur:
            cur.execute(
                """
                SELECT ss.symbol, ss.composite_score, ss.quality_score, ss.growth_score,
                       ss.risk_score, ss.momentum_score, ss.components,
                       ss.data_completeness, ss.data_unavailable, ss.unavailable_metrics
                FROM stock_scores ss
                JOIN value_metrics vm ON vm.symbol = ss.symbol
                JOIN stock_symbols su ON su.symbol = ss.symbol
                LEFT JOIN company_info_sec cis ON cis.symbol = ss.symbol
                LEFT JOIN (
                    SELECT symbol,
                           AVG(volume * close) AS avg_dollar_volume_20d,
                           (ARRAY_AGG(close ORDER BY date DESC))[1] AS latest_close
                    FROM (
                        SELECT symbol, volume, close, date,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                        FROM price_daily
                        WHERE date >= CURRENT_DATE - INTERVAL '45 days'
                          AND COALESCE(data_unavailable, false) = false
                          AND volume IS NOT NULL AND close IS NOT NULL
                    ) ranked
                    WHERE rn <= 20
                    GROUP BY symbol
                ) liq_floor ON liq_floor.symbol = ss.symbol
                WHERE ss.value_score IS NOT NULL
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
            # No work to do - every scored symbol already cleared the liquidity floor and the
            # non-operating exclusion, so there's nothing to withhold this run. Not an error.
            return []

        min_completeness_threshold = getattr(self, "_min_completeness_threshold", 70.0)
        withheld: list[tuple[str, float | None, float, str | None, float, bool, str, str | None]] = []
        for (
            symbol,
            _composite_score_old,
            quality_score,
            growth_score,
            risk_score,
            momentum_score,
            components_old,
            _dc_old,
            _du_old,
            unavailable_metrics_old_raw,
        ) in rows:
            # GROWTH RESTORED TO COMPOSITE 2026-09-17 (same-day reversal - see
            # pillar_weights.py's BASE_PILLAR_WEIGHTS "ABOVE DECISION SUPERSEDED" note).
            weights = BASE_PILLAR_WEIGHTS
            pillar_scores = (
                ("quality", quality_score),
                ("risk", risk_score),
                ("momentum", momentum_score),
                ("growth", growth_score),
            )
            composite_val = sum(float(s) * weights[p] for p, s in pillar_scores if s is not None)
            composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)
            available_weight = sum(weights[p] for p, s in pillar_scores if s is not None)
            data_completeness_new = min(99.99, round(available_weight * 100, 2))
            data_unavailable_new = data_completeness_new < min_completeness_threshold

            unavailable_metrics_new = dict(unavailable_metrics_old_raw) if unavailable_metrics_old_raw else {}
            unavailable_metrics_new["value"] = "value_below_liquidity_floor"
            reason_new = (
                f"Completeness {data_completeness_new:.2f}% < {min_completeness_threshold}% "
                f"threshold (missing metrics: {', '.join(sorted(unavailable_metrics_new.keys()))})"
                if data_unavailable_new
                else None
            )
            components_json = self._components_with_corrected_value(components_old, None)
            withheld.append(
                (
                    symbol,
                    None,
                    composite_score_new,
                    components_json,
                    data_completeness_new,
                    data_unavailable_new,
                    json.dumps(unavailable_metrics_new),
                    reason_new,
                )
            )
        logger.info(
            f"[STOCK_SCORES] Value: withheld value_score for {len(withheld)} symbols below the "
            f"liquidity floor / excluded from the scoring population (never reached by the "
            f"correction pass above) - see _withhold_value_below_floor's docstring."
        )
        return withheld
