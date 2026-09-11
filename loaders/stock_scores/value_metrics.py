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

from loaders.stock_scores.pillar_weights import BASE_PILLAR_WEIGHTS, _value_risk_adjusted_weights
from loaders.stock_scores.value_score import VALUE_MIN_WEIGHT, _dividend_sustainability_factor
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
        - Row length validation: Must have 16 columns (pe_ratio, pb_ratio, ps_ratio, peg_ratio,
          dividend_yield, fcf_yield, forward_pe, ev_ebitda, ev_revenue, margin_of_safety_pct,
          market_cap, net_payout_yield, pe_ratio_unavailable_reason,
          forward_pe_unavailable_reason, pb_ratio_unavailable_reason, data_unavailable) - the
          pe_ratio/forward_pe *_unavailable_reason columns were added 2026-08-28 to distinguish
          "genuinely missing data" from "unprofitable company / negative earnings forecast" for
          P/E and Forward P/E (see _score_value's "UNPROFITABLE-COMPANY FLOOR ADDED 2026-08-28"
          docstring note); pb_ratio_unavailable_reason added 2026-09-05 for the identical
          negative-book-value case, previously missing here entirely.
        - Schema mismatch (len(row) < 16) → raises ValueError immediately
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
            # added 2026-09-05 - see _score_value's docstring)
            if len(row) < 16:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: value_metrics row has {len(row)} columns, expected 16. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[15]
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
            }
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No value metrics available for {symbol} - score completeness will be reduced"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_metrics_found"}

    @staticmethod
    def _pe_curve_score(pe: float) -> float:
        """PROVISIONAL fixed-threshold P/E score (see _score_value's PE block comment) - used
        as this symbol's Pass-1 placeholder only. UPDATED 2026-08-31 (see
        update_value_multiples_percentiles()'s "BUG FOUND + FIXED 2026-08-31" docstring note):
        that method now fully recomputes value_score from percentile ranks each time rather
        than diffing against this function's output, so this formula is free to change without
        touching that reconciliation - it only affects Pass-1's provisional value."""
        if pe <= 10:
            return 40 + pe * 2  # very cheap / possibly value trap
        if pe <= 20:
            return 60 + (pe - 10) * 4  # good range
        if pe <= 35:
            return 100 - (pe - 20) * 2  # growth premium zone -> 70 at pe=35
        return max(0.0, 70 - (pe - 35) * 1.4)  # expensive -> 0 at pe~85

    @staticmethod
    def _pb_curve_score(pb: float) -> float:
        """PROVISIONAL fixed-threshold P/B score - see `_pe_curve_score`'s docstring for why
        this must stay unchanged independent of the live scoring path."""
        if pb <= 1.0:
            return 100.0
        if pb <= 3.0:
            return 100 - ((pb - 1.0) / 2.0) * 30  # 100->70 in [1,3]
        if pb <= 7.0:
            return 70 - ((pb - 3.0) / 4.0) * 40  # 70->30 in [3,7]
        return max(0.0, 30 - (pb - 7.0) * 3)

    @staticmethod
    def _ps_curve_score(ps: float) -> float:
        """PROVISIONAL fixed-threshold P/S score - see `_pe_curve_score`'s docstring for why
        this must stay unchanged independent of the live scoring path."""
        if ps <= 2.0:
            return 100.0
        if ps <= 6.0:
            return 100 - ((ps - 2.0) / 4.0) * 30  # 100->70 in [2,6]
        if ps <= 15.0:
            return 70 - ((ps - 6.0) / 9.0) * 40  # 70->30 in [6,15]
        return max(0.0, 30 - (ps - 15.0) * 1.5)

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
        cls, values: dict[str, float], sector_map: dict[str, str]
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
        """
        groups: dict[str, list[str]] = {}
        residual: dict[str, float] = {}
        for symbol, val in values.items():
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
        """Batch pass: replace P/E, P/B, P/S, and Forward P/E's Pass-1 PROVISIONAL fixed-curve
        scores with a true cross-sectional percentile rank against the current run's universe,
        then FULLY RECOMPUTE value_score and composite_score from scratch off the raw stored
        inputs (not patched relative to whatever value_score/composite_score currently hold).
        Mirrors `update_rs_percentiles()`'s pure-overwrite pattern, not the additive-delta
        design this method used until the rewrite below - see "BUG FOUND + FIXED 2026-08-31"
        below.

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
        still uses `_pe_curve_score`/`_pb_curve_score`/`_ps_curve_score` (the last one reused for
        Forward P/E too, same curve, see that field's own docstring note) as a PROVISIONAL
        placeholder so value_score/composite_score are never NULL mid-run. This method runs
        after every symbol in this run has a value_score, computes the true cross-sectional
        percentile per ratio (independently - a symbol missing P/B still gets ranked on P/E and
        P/S), and FULLY RECOMPUTES value_score from the percentile scores plus dividend_yield's
        own unchanged curve score (the only Value sub-component this pass doesn't replace),
        weighted exactly as `_score_value` itself weights them (12/39/34/4/11). composite_score
        is then independently recomputed in full from quality_score/growth_score/risk_score/
        momentum_score (read as-is, untouched by this pass) plus the new value_score, via
        `_value_risk_adjusted_weights` - the same weighting `_score_value`'s own caller uses,
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
                           ss.components, cp.sector, ss.data_completeness, ss.data_unavailable,
                           ss.unavailable_metrics
                    FROM stock_scores ss
                    JOIN value_metrics vm ON vm.symbol = ss.symbol
                    LEFT JOIN company_profile cp ON cp.symbol = ss.symbol
                    JOIN stock_symbols su ON su.symbol = ss.symbol
                    LEFT JOIN company_info_sec cis ON cis.symbol = ss.symbol
                    WHERE ss.value_score IS NOT NULL
                      AND COALESCE(vm.data_unavailable, false) = false
                      AND ("""
                    + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                    + ")"
                )
                rows = cur.fetchall()

            if not rows:
                logger.warning(
                    "[STOCK_SCORES] update_value_multiples_percentiles: no eligible rows found "
                    "(value_score IS NOT NULL joined to value_metrics) - skipping, nothing to correct."
                )
                return

            pe_raw: dict[str, float] = {}
            pb_raw: dict[str, float] = {}
            ps_raw: dict[str, float] = {}
            fwd_pe_raw: dict[str, float] = {}
            # unprofitable_symbols/negative_fwd_symbols: floored at percentile 0.0 directly
            # below (not run through _percent_rank_cheap_high) - see _score_value's
            # "UNPROFITABLE-COMPANY FLOOR ADDED 2026-08-28" docstring note for why a floor
            # (not exclusion) is the theoretically correct treatment here.
            unprofitable_symbols: set[str] = set()
            negative_fwd_symbols: set[str] = set()
            sector_map: dict[str, str] = {}
            for row in rows:
                symbol, pe, pb, ps, fwd_pe = row[0], row[7], row[8], row[9], row[10]
                pe_reason, fwd_pe_reason = row[13], row[14]
                sector = row[16]
                if sector is not None:
                    sector_map[symbol] = sector
                if pe is not None and float(pe) > 0:
                    pe_raw[symbol] = float(pe)
                elif pe_reason == "unprofitable_stock":
                    unprofitable_symbols.add(symbol)
                if pb is not None and float(pb) > 0:
                    pb_raw[symbol] = float(pb)
                if ps is not None and float(ps) > 0:
                    ps_raw[symbol] = float(ps)
                if fwd_pe is not None and float(fwd_pe) > 0:
                    fwd_pe_raw[symbol] = float(fwd_pe)
                elif fwd_pe_reason == "negative_forward_eps":
                    negative_fwd_symbols.add(symbol)

            pe_pct = self._percent_rank_cheap_high_sector_relative(pe_raw, sector_map)
            pb_pct = self._percent_rank_cheap_high_sector_relative(pb_raw, sector_map)
            ps_pct = self._percent_rank_cheap_high_sector_relative(ps_raw, sector_map)
            fwd_pe_pct = self._percent_rank_cheap_high_sector_relative(fwd_pe_raw, sector_map)
            for symbol in unprofitable_symbols:
                pe_pct[symbol] = 0.0
            for symbol in negative_fwd_symbols:
                fwd_pe_pct[symbol] = 0.0
            logger.info(
                f"[STOCK_SCORES] Value multiples percentile universe (sector-relative, "
                f"{len(sector_map)}/{len(rows)} symbols mapped to a GICS sector): "
                f"P/E {len(pe_pct)} ({len(unprofitable_symbols)} floored unprofitable), "
                f"P/B {len(pb_pct)}, P/S {len(ps_pct)}, "
                f"Forward P/E {len(fwd_pe_pct)} ({len(negative_fwd_symbols)} floored negative-forecast) symbols"
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
                pe, pb, ps, fwd_pe, dividend_yield = row[7], row[8], row[9], row[10], row[11]
                fcf_yield = safe_float(row[12], f"{symbol}.fcf_yield") if row[12] is not None else None
                pe_reason, fwd_pe_reason = row[13], row[14]
                components_old = row[15]
                data_completeness_old = float(row[17]) if row[17] is not None else None
                data_unavailable_old = bool(row[18]) if row[18] is not None else False
                unavailable_metrics_old: dict[str, str] = dict(row[19]) if row[19] else {}
                value_score_old = float(value_score_old)
                composite_score_old = float(composite_score_old)

                # Pure recompute of value_score from the raw stored inputs - percentile rank
                # for PE/PB/PS/forward_pe, dividend's own unchanged curve score (_score_value's
                # own formula, see that method) - value_score_old is read above only to detect
                # whether anything changed, never as an input to the new value. See "BUG FOUND
                # + FIXED 2026-08-31" docstring note above for why this replaced the prior
                # additive-delta-on-a-mutable-column design.
                # UNIFORM EQUAL-WEIGHT (2026-09-11, user directive - see pillar_weights.py's
                # BASE_PILLAR_WEIGHTS comment for the full rationale, and _score_value's own
                # matching note). All 5 components (PE/PB/PS/Forward PE/Dividend Yield) are now
                # flat 20% each - mirrors _score_value's Pass-1 weights exactly. Keep both passes
                # in sync if either changes.
                components: list[tuple[float, float]] = []
                if pe is not None and float(pe) > 0:
                    components.append((pe_pct[symbol], 0.20))
                elif pe_reason == "unprofitable_stock":
                    components.append((0.0, 0.20))
                if pb is not None and float(pb) > 0:
                    components.append((pb_pct[symbol], 0.20))
                if ps is not None and float(ps) > 0:
                    components.append((ps_pct[symbol], 0.20))
                if fwd_pe is not None and float(fwd_pe) > 0:
                    components.append((fwd_pe_pct[symbol], 0.20))
                elif fwd_pe_reason == "negative_forward_eps":
                    components.append((0.0, 0.20))
                # FIXED 2026-08-31 (same fix, same reasoning as _score_value's own dividend
                # block above - value_metrics.dividend_yield is a real, already-computed 0.0
                # for non-payers, never NULL, so a `> 0` gate wrongly reweighted this term away
                # for 56% of the universe instead of scoring the real 0% floor).
                # TRIMMED 11%->8% 2026-08-31, RAISED 8%->10% 2026-09-01 (equal-weight reweight
                # above) - weak evidence, kept at user directive, sized as a satellite weight.
                if dividend_yield is not None:
                    div = min(float(dividend_yield) * 100, 6)  # decimal -> percent, cap 6%
                    div_score = min(100, div * 16.7)
                    # REAL-MONEY-READINESS FIX 2026-09-08: this recompute pass unconditionally
                    # overwrote _score_value's gated value_score with this magnitude-only
                    # dividend term, silently undoing the CATO value-trap payout-sustainability
                    # gate (value_score.py's _dividend_sustainability_factor) on every run of
                    # this post_run() pass - the exact stock that gate exists to catch (high
                    # yield funded by negative FCF) got its full ungated score written to the
                    # real stock_scores/composite_score row that trading reads.
                    div_score *= _dividend_sustainability_factor(float(dividend_yield), fcf_yield)
                    components.append((div_score, 0.20))

                total_weight = sum(w for _, w in components)
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
                    value_score_new = round(max(0.0, min(100.0, sum(v * w for v, w in components) / total_weight)), 2)

                # Pure recompute of composite_score from the 5 pillar scores as they currently
                # stand in stock_scores (quality/growth/risk/momentum are untouched by this
                # pass - only value_score changed above), mirroring _score_value's own caller
                # (no weight redistribution for a missing pillar - GOVERNANCE rule, same as
                # Pass 1) instead of patching composite_score_old by a delta.
                risk_score_float = float(risk_score) if risk_score is not None else None
                weights = _value_risk_adjusted_weights(risk_score_float)
                composite_val = 0.0
                for pillar_name, pillar_score in (
                    ("quality", quality_score),
                    ("growth", growth_score),
                    ("value", value_score_new),
                    ("risk", risk_score),
                    ("momentum", momentum_score),
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
                    "growth": float(growth_score) if growth_score is not None else None,
                    "value": value_score_new,
                    "risk": float(risk_score) if risk_score is not None else None,
                    "momentum": float(momentum_score) if momentum_score is not None else None,
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

            if not updates:
                logger.info(
                    "[STOCK_SCORES] Value multiples percentile pass: no symbol's value_score/"
                    "composite_score changed (expected on a repeat run with unchanged inputs - "
                    "this pass is now idempotent, see its 'BUG FOUND + FIXED 2026-08-31' note)."
                )
                return

            with _owner().DatabaseContext("write") as cur:
                _owner().execute_values(
                    cur,
                    """
                    UPDATE stock_scores AS ss
                    SET value_score = v.value_score,
                        composite_score = v.composite_score,
                        components = v.components::jsonb,
                        data_completeness = v.data_completeness,
                        data_unavailable = v.data_unavailable,
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
