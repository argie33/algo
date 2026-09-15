"""MomentumScoringMixin, extracted from load_stock_scores.py (2026-09-05, file-size-ratchet
bloaters-decomposition split). Moved verbatim - no behavior change - except
`DatabaseContext(...)` call site in update_rs_percentiles now goes through `_owner()` (see that
helper's own docstring for why).

Mixed into StockScoresLoader alongside the other stock_scores/*.py pillar mixins - every
`self.` reference here resolves normally through the instance regardless of which mixin file
defines it.
"""

import json
import logging
import math
from typing import TYPE_CHECKING, Any

import psycopg2

from loaders.helpers.factor_normalization import universe_wide_zscore, zscore_to_percentile_scale
from loaders.stock_scores.pillar_weights import (
    BASE_PILLAR_WEIGHTS,
    DEFAULT_MIN_INVESTABLE_MARKET_CAP,
    _value_risk_adjusted_weights,
)
from utils.loaders.helpers import NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE
from utils.type_conversion import safe_float

logger = logging.getLogger("loaders.load_stock_scores")

# MOMENTUM_MIN_WEIGHT (added 2026-09-07, /goal real-money-readiness audit): same thin-sample-
# extrapolation gate already applied to Value (VALUE_MIN_WEIGHT), Growth
# (GROWTH_MIN_FIELDS_AVAILABLE), and Risk (RISK_MIN_WEIGHT_AVAILABLE) - _score_momentum's old
# `if total_weight > 0: return weighted_sum / total_weight` treated ANY nonzero nominal weight
# as a fully-confident 0-100 score, including a single near-zero MACD-sign reading (0.37
# weight) with no price-return momentum, no RSI, no SMA data at all. Live-confirmed: NCPL and
# 7 similar thin-coverage symbols (XLAB/CURX/PAAI/SGLD/BOXL/PSQL/VAI) scored momentum_score=70
# flat off nothing but "MACD is barely positive". Same 0.40 floor as Value/Risk (~40% of
# nominal weight is this file's established floor for "the score reflects the pillar's actual
# construction, not a fragment of it").
MOMENTUM_MIN_WEIGHT = 0.40

# RISK-ADJUSTED MOMENTUM (added 2026-09-14, goal-session backtest validation): MSCI's real
# Momentum Index construction divides each price-return window by realized volatility before
# combining (a Sharpe-ratio-style risk adjustment), not raw returns - see
# algo/research/momentum_risk_adjusted_ic_test_20260914.py for the isolated fit(2017-2021)/
# holdout(2022-2026) backtest that validated this: real, consistent, modest IC improvement in
# every period tested before this was ported to live scoring (composite IC 0.0130->0.0140 full
# sample, 0.0058->0.0069 fit, 0.0200->0.0209 holdout).
#
# Live scoring has no z-score step to plug a risk-adjusted RATIO into unlike that research
# script's cross-sectional pipeline - _pct_to_score's curve is calibrated for raw percentage
# returns (-20%=0, +20%=100), and a risk-adjusted ratio (return/vol, e.g. 0.15/0.30=0.5) is on
# a completely different numeric scale that would silently miscalibrate the whole curve if fed
# in directly. MEDIAN_UNIVERSE_VOL_252D (0.5447, live-measured from stability_metrics.
# volatility_252d across 5,040 real scored symbols, 2026-09-14) is the renormalization anchor:
# multiplying the risk-adjusted ratio back up by this constant converts it back into
# "percentage-return-equivalent" units so the EXISTING curve stays valid - an exactly-average-
# volatility stock's score is unchanged from before this fix, a below-median-vol stock's same
# raw return now scores HIGHER (cheaper per unit risk), and an above-median-vol stock's same
# raw return scores LOWER - the intended risk adjustment, without redesigning the curve itself.
MEDIAN_UNIVERSE_VOL_252D = 0.5447
# FROZEN-CONSTANT DRIFT (flagged by peer review same day, fixed before shipping): real factor
# indices recompute this kind of cross-sectional statistic at every rebalance rather than
# freezing it - a hardcoded snapshot would silently drift stale as the universe's volatility
# regime shifts (e.g. a broad low-vol stretch would push every symbol's multiplier the same
# direction, not stay centered). `_get_median_vol_252d` below recomputes this from
# self._stability_cache (already batch-loaded by _prepare_batch_context) fresh on every scoring
# run - this constant now only serves as the fallback for contexts where that cache isn't
# populated (isolated unit tests, or a genuinely empty batch), not as the value live scoring
# actually uses.
# Floor on vol_252d before using it as a divisor - guards the same near-zero-volatility
# measurement-validity concern already documented for Risk's own vol scoring
# (risk_scoring.py's NEAR_ZERO_LIQUIDITY_THRESHOLD/frozen-price gate): a frozen/near-frozen
# price would otherwise blow up the risk-adjustment ratio, not reflect a genuinely safer return.
MIN_VOL_252D_FOR_RISK_ADJUSTMENT = 0.05
# Cap on the risk-adjustment MULTIPLIER itself (MEDIAN_UNIVERSE_VOL_252D / vol_252d), not just
# the floor on vol_252d - live-caught 2026-09-14 sanity check BEFORE this shipped: a real
# low-vol utility (TXNM, vol_252d=0.051, just above the floor) got amplified 10.7x
# (0.5447/0.051), pushing a modest raw return straight to curve saturation (delta +25.85 on a
# 0-100 score from one sub-component) - not a genuine risk-adjustment signal, an artifact of
# dividing by a number close to the floor. Same "winsorize extreme ratios" discipline this
# codebase already applies everywhere else a peer-relative ratio is computed
# (_winsorize_group/_winsorize_group_values clip to [1st,99th] percentile).
#
# FIXED same day (goal-session code-quality pass): the original version of this fix hardcoded
# [0.5x, 2.0x] here, reasoning "this pillar scores one symbol against a fixed curve, not a peer
# group, so there's no cross-sectional population to compute a percentile from" - but that's
# wrong. self._stability_cache already holds the WHOLE batch's vol_252d values (that's exactly
# what MEDIAN_UNIVERSE_VOL_252D's own median is computed from, one function below), so the
# batch's own distribution of median_vol/vol_252d ratios is available for a real [1st,99th]
# percentile clip via _winsorize_group's same _percentile() method - the exact "population will
# drift, hardcoded number won't" risk this same commit already called out and fixed for the
# median one paragraph above, left unaddressed for the cap. `_get_risk_adjustment_multiplier_bounds`
# below computes that live; these two constants are now only the fallback for an unpopulated
# batch (isolated unit tests) or a batch too thin to trust a percentile from (<5 symbols, same
# floor _winsorize_group itself uses).
MAX_RISK_ADJUSTMENT_MULTIPLIER = 2.0
MIN_RISK_ADJUSTMENT_MULTIPLIER = 0.5


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


class MomentumScoringMixin:
    """See module docstring.

    `_technical_cache`/`_momentum_cache` are set on the instance by `_prepare_batch_context`
    (defined on StockScoresLoader itself, not any mixin) - declared type-checking-only below
    so mypy can see them without a real circular import.
    """

    if TYPE_CHECKING:
        _technical_cache: dict[str, tuple[Any, ...]]
        _momentum_cache: dict[str, tuple[Any, ...]]
        _stability_cache: dict[str, tuple[Any, ...]]
        _median_vol_252d_cache: float | None
        _risk_adjustment_multiplier_bounds_cache: tuple[float, float] | None

    def _get_momentum_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch momentum/RS metrics for symbol from momentum_metrics table.

        CRITICAL FIX 2026-07-18: Now reads precomputed momentum values from momentum_metrics
        table (populated by load_risk_metrics_daily.py) instead of computing from scratch.
        This fixes the issue where stock_scores had all NULL momentum despite momentum_metrics
        being populated.

        momentum_metrics provides:
        - momentum_1m, momentum_3m, momentum_6m, momentum_12m (already calculated)
        - data_unavailable flag (True if loader failed)

        Also merges in the latest RSI(14)/MACD/SMA-positioning from technical_data_daily (via
        self._technical_cache). These are a separate, independently-available source, so a
        symbol without usable price-return momentum can still contribute an RSI/MACD/SMA-only
        momentum score, and vice versa.

        UNIFIED 2026-08-28 (goal: momentum/risk factor logic review): this method used to treat
        "no momentum_metrics row at all for this symbol" and "momentum_metrics row present but
        data_unavailable=True" as two DIFFERENT cases with opposite outcomes - the former (added
        Session 416, 2026-07-25, "CRITICAL: Remove 7 silent fallback violations") returned a hard
        data_unavailable marker even when RSI/MACD were available, citing GOVERNANCE.md's
        no-secondary-fallback rule ("RSI/MACD are oscillators... not price-return momentum...
        substituting creates false signal diversification"); the latter (added 2026-07-20, never
        revisited by the Session 416 audit) kept scoring RSI/MACD/SMA as a partial momentum score
        in the exact same real-world situation. Two branches, same underlying condition (no
        price-return momentum for this symbol), opposite treatment - purely because of which of
        two upstream code paths happened to produce it, not because of any real signal-quality
        difference. That reasoning doesn't actually hold under GOVERNANCE's own rule: RSI/MACD/
        SMA are not substituting FOR price-return momentum here - they carry their own dedicated,
        independent weight slots in _score_momentum (21%/16%/8% = 45% combined) that are already
        scored alongside price-return momentum whenever ALL of it is present, so their
        contribution when price-return momentum alone is missing isn't a proxy fallback, it's the
        same self-normalizing "score what's independently available, drop what's missing" pattern
        every other pillar in this file already uses (see _score_risk's own docstring for the
        same principle stated explicitly). GOVERNANCE's actual no-fallback example ("short-term
        momentum when long-term unavailable") describes swapping one proxy for a structurally
        similar metric within the SAME family, which this isn't.
        Verified empirically before unifying (live local DB, exclude_etfs=True universe matching
        what this loader actually processes): 5,102/5,102 real-stock-universe symbols already
        have a momentum_metrics row (0 hit the old "row absent" branch at all - it was live dead
        code for the current universe); 30/5,102 are row-present-but-data_unavailable (the only
        branch that ever actually fired). So today's live scores are unaffected by this change -
        it closes a latent inconsistency (a landmine if the momentum_metrics/stock_scores
        universes ever drift apart) rather than changing any symbol's current score. Both cases
        now go through one shared path below.

        Returns dict with momentum values (which may be None for individual timeframes if
        upstream loader failed to calculate them).
        """
        try:
            tech_row = self._technical_cache.get(symbol, None)
            rsi_14 = safe_float(tech_row[0], f"{symbol}.rsi_14", allow_none=True) if tech_row else None
            macd = safe_float(tech_row[1], f"{symbol}.macd", allow_none=True) if tech_row else None
            sma_50 = safe_float(tech_row[2], f"{symbol}.sma_50", allow_none=True) if tech_row else None
            sma_200 = safe_float(tech_row[3], f"{symbol}.sma_200", allow_none=True) if tech_row else None
            close = safe_float(tech_row[4], f"{symbol}.close", allow_none=True) if tech_row else None
            # Decimal fraction (0.05 = +5%), matching _score_momentum's ±10%-range-maps-to-0-100
            # formula - NOT the *100 percentage scale the scores API computes for display.
            price_vs_sma_50 = (close - sma_50) / sma_50 if close is not None and sma_50 else None
            price_vs_sma_200 = (close - sma_200) / sma_200 if close is not None and sma_200 else None

            # vol_252d (annualized, decimal fraction e.g. 0.30 = 30%) from stability_metrics,
            # already batch-loaded onto self._stability_cache by _prepare_batch_context (see
            # load_stock_scores.py's own SELECT - index 0 of the cached tuple is volatility_252d,
            # the query's first column after symbol). Used below to risk-adjust mom_3m/mom_12_1 -
            # see RISK-ADJUSTED MOMENTUM docstring note in _score_momentum for why.
            stability_row = getattr(self, "_stability_cache", {}).get(symbol)
            vol_252d = (
                safe_float(stability_row[0], f"{symbol}.volatility_252d", allow_none=True) if stability_row else None
            )

            row = self._momentum_cache.get(symbol, None)

            if row is not None:
                # momentum_metrics cache has 5 columns: momentum_1m, momentum_3m, momentum_6m, momentum_12m, data_unavailable
                if len(row) < 5:
                    raise ValueError(
                        f"[STOCK_SCORES] {symbol}: momentum cache returned {len(row)} columns, expected 5. "
                        f"Schema mismatch detected. Failing fast."
                    )

                momentum_1m = safe_float(row[0], f"{symbol}.momentum_1m", allow_none=True)
                momentum_3m = safe_float(row[1], f"{symbol}.momentum_3m", allow_none=True)
                momentum_6m = safe_float(row[2], f"{symbol}.momentum_6m", allow_none=True)
                momentum_12m = safe_float(row[3], f"{symbol}.momentum_12m", allow_none=True)
                price_momentum_unavailable = bool(row[4])
                no_row_reason = "momentum_metrics_loader_failed"
            else:
                # No momentum_metrics row at all for this symbol. Treated identically to
                # row-present-but-data_unavailable=True below (see UNIFIED 2026-08-28 docstring
                # note above) - both mean "no price-return momentum for this symbol", and RSI/
                # MACD/SMA are independently scored either way, not substituted in as a proxy.
                momentum_1m = momentum_3m = momentum_6m = momentum_12m = None
                price_momentum_unavailable = True
                no_row_reason = "no_momentum_data_available"

            if price_momentum_unavailable:
                if rsi_14 is None and macd is None and price_vs_sma_50 is None and price_vs_sma_200 is None:
                    logger.warning(
                        f"[LOAD_STOCK_SCORES] No momentum data available for {symbol} - "
                        f"neither price-return momentum nor RSI/MACD/SMA positioning is usable."
                    )
                    return {"symbol": symbol, "data_unavailable": True, "reason": no_row_reason}
                return {
                    "momentum_1m": None,
                    "momentum_3m": None,
                    "momentum_6m": None,
                    "momentum_12m": None,
                    "rsi_14": rsi_14,
                    "macd": macd,
                    "price_vs_sma_50": price_vs_sma_50,
                    "price_vs_sma_200": price_vs_sma_200,
                    "vol_252d": vol_252d,
                }

            return {
                "momentum_1m": momentum_1m,
                "momentum_3m": momentum_3m,
                "momentum_6m": momentum_6m,
                "momentum_12m": momentum_12m,
                "rsi_14": rsi_14,
                "macd": macd,
                "price_vs_sma_50": price_vs_sma_50,
                "price_vs_sma_200": price_vs_sma_200,
                "vol_252d": vol_252d,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database operation failed fetching momentum metrics for {symbol}: {e}") from e

    def _score_momentum(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score momentum metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted scoring: Momentum 3m (20%) + 12-1 skip-month momentum (45%) + RSI(14)/
        MACD-sign technical-trend confirmation (15% combined, averaged - see CONSOLIDATED
        2026-08-28 note below) + SMA positioning (20%) - see "MOM_12_1 RE-EMPHASIZED, TECH_TREND
        DEMOTED" note below for the 2026-09-14 industry-consensus rationale. Normalizes by total
        weight of available components so partial data doesn't deflate the score. Raw
        momentum_6m/momentum_12m REPLACED 2026-08-25 by a derived 12-1 construction - see
        RESOLVED note below.

        CONSOLIDATED 2026-08-28 (goal: momentum/risk factor-interaction review, closing a gap
        this file's own 2026-08-25 audit flagged and never finished - see "OPEN QUESTION
        flagged 2026-08-25" below: that FM panel found rsi_14/macd_sign correlated r=0.70, and
        their multivariate coefficients literally flip sign against each other under joint
        estimation (macd_sign t=-0.37 alone vs t=+2.95 jointly) - the textbook symptom of two
        inputs carrying substantially the same information, not two independent ones. That
        audit's own conclusion was "the right fix here is a consolidation pass ... before any
        reweighting", but only the momentum-window half of that pass (6m/12m -> 12-1, see
        RESOLVED note below) was ever actually done - RSI/MACD were left as two independently-
        weighted 21%/16% terms despite being named in the same finding. Live-reverified before
        acting, not trusted from a 3-day-old docstring number alone: current DB, rsi_14 vs
        (macd>0) Pearson r=0.58 (n=10,796, latest technical_data_daily row per symbol) - same
        conclusion, real and current, not a stale claim. Fixed the same way this pillar's own
        price_vs_sma_50/200 (r=0.87, same OPEN QUESTION) and Risk's six volatility windows
        (r=0.52-0.92) were already fixed: average the two 0-100 sub-scores into one slot
        instead of weighting each independently. Combined weight unchanged (21%+16%=37%) - a
        redundancy fix, not a new claim about RSI vs. MACD's relative signal strength.

        REDESIGNED 2026-08-25 (goal: full scoring-architecture audit): momentum_1m and the
        ROC composite both removed. ROC composite was pure redundancy - roc_20d/60d/120d/252d
        are the same `close.pct_change()` computation as momentum_1m/3m/6m/12m over
        near-identical trading-day windows, so it was the same 4 return windows counted a
        second time, not a diversifying signal. momentum_1m was dropped separately per the
        standard academic 12-1 momentum construction (Jegadeesh 1990 short-term reversal) -
        see the weights dict below for the empirical confirmation in our own data.

        OPEN QUESTION flagged 2026-08-25 (same day, later pass - goal: re-audit ALL stock_scores
        inputs without bias toward what already shipped): built
        algo/research/fama_macbeth_momentum_factors.py - reconstructs RSI(14)/MACD/SMA(50,200)
        directly from price_daily (Wilder 1978 RSI convention, standard 12/26/9 MACD EMAs) so
        the ENTIRE live Momentum input set (not just the 3m/6m/12m windows tested in
        fama_macbeth_price_factors.py) could be regressed jointly for the first time. Found
        severe multicollinearity, measured directly (121-month pooled correlation matrix):
        mom_12m/mom_6m r=0.83, rsi_14/macd_sign r=0.70, price_vs_sma_50/200 r=0.87,
        mom_3m/mom_6m r=0.69 - comparable in magnitude to the 0.52-0.92 range that justified
        consolidating Stability's 6 volatility windows down to 2, except this pillar's 6 inputs
        never got that treatment. Consequence: multivariate FM coefficients for mom_6m,
        macd_sign, and price_vs_sma_200 all FLIP SIGN between univariate and multivariate specs
        (e.g. macd_sign t=-0.37 alone vs t=+2.95 controlling for the others) - a classic
        collinearity symptom, meaning none of those multivariate coefficients are trustworthy
        standalone evidence for reweighting. The one factor that stayed directionally stable
        both ways was rsi_14 (t=-1.83 univariate, -1.89 multivariate) - consistently NEGATIVE,
        i.e. high RSI (overbought) weakly predicts LOWER forward return in this data, the
        mean-reversion/oscillator interpretation Wilder originally designed RSI for, not this
        pillar's current trend-following "higher RSI = more bullish" treatment. Lower
        evidentiary tier than the JoF-grade factors elsewhere in this file though - RSI is a
        technical-analysis heuristic without the same academic asset-pricing literature behind
        it, so this is an internal-data finding, not a replicated anomaly. The right fix here
        is a consolidation pass (fewer, less-redundant inputs, same treatment Stability
        already got) before any reweighting - extracting weights from an unstable collinear
        regression would just encode noise (see RESOLVED note below for what was actually
        done). (Growth's open question, previously cited here as the same-tier companion
        item, is now resolved - see that pillar's docstring.)

        CONFIRMATORY RE-RUN 2026-08-25 (same-day follow-up, goal: check whether this needed
        more than a re-statement before the next session touches it): re-ran
        fama_macbeth_momentum_factors.py fresh rather than relying on the numbers above.
        Univariate results for the four return-window factors are ALL statistically
        indistinguishable from zero: mom_12_1 (proper Jegadeesh 1990 skip-month construction,
        not a live input at the time of this run) t=1.04, mom_3m t=-0.88, mom_6m t=-0.38,
        mom_12m t=0.38 - none exceed |t|=1.1, so there is no "drop the weakest, keep the
        strongest" call available from significance alone (unlike Value's clean PB-is-most-
        distinct finding). mom_12_1 was nominally the strongest of the four - suggestive, not
        conclusive on significance, but real: it's the actual literature-standard momentum
        construction (Jegadeesh 1990/Jegadeesh-Titman 1993/Carhart 1997 UMD), not an ad hoc
        pick, independent of whether this internal sample confirms it.

        RESOLVED 2026-08-25 (same-day follow-up, acting on the next-step spec above):
        momentum_6m and momentum_12m REPLACED by a derived 12-1 skip-month construction,
        following the exact same "collapse redundant windows, keep the total category weight"
        treatment already applied to Stability's 6 volatility windows. momentum_6m was the
        most redundant "middle" window (r=0.69 with 3m, r=0.83 with 12m - correlated with
        both neighbors, contributing the least unique information of the three) and
        momentum_12m's simple trailing-return construction is exactly the recency-
        contaminated shape this pillar's docstring already flagged as a problem when it
        dropped momentum_1m for the same Jegadeesh 1990 reason above - that reasoning was
        never carried through to fix the 12m window itself until now. No new stored field
        needed: mom_12_1 (cumulative return from 12mo-ago to 1mo-ago) is algebraically
        derivable from momentum_12m and momentum_1m, both already fetched here -
        ((1+momentum_12m/100)/(1+momentum_1m/100) - 1)*100. Weight 35% = the exact combined
        weight momentum_6m(20%) + momentum_12m(15%) previously carried - a straight
        consolidation of the redundant windows' weight into the literature-correct
        construction, not a new claim about relative signal strength (this data's own
        univariate test above found none of the four constructions individually
        significant - the redistribution rests on redundancy + literature convention, the
        same evidentiary bar Stability's consolidation used, not on this session's t-stats).
        momentum_3m kept unchanged (least correlated of the trio, r=0.69 with 6m, a genuine
        short-horizon complement to the now-proper long-horizon signal).

        RSI SIGN QUESTION - sub-period-checked same session (same method that closed
        Stability's max_drawdown_1y question, see that pillar's docstring): unlike
        max_drawdown_1y, rsi_14's negative univariate coefficient is NOT a sign flip - it's
        directionally consistent negative in 3 of 4 sub-samples (full sample t=-1.91, first
        half 2016-06/2021-06 t=-2.07, tercile 1 t=-1.54, tercile 2 t=-1.60) but fades to
        indistinguishable-from-zero in the most recent ~3.5 years (second half t=-0.45,
        tercile 3 2023-02/2026-07 t=+0.08) - a decaying-but-not-reversing pattern, not noise
        flipping sign. Still NOT flipping this pillar's "higher RSI = more bullish" treatment:
        (1) even the strongest historical reading (t≈-2) is a technical-analysis heuristic
        without the JoF-grade literature backing behind Value/Growth's anomalies, (2) the
        effect is weakest exactly in the most recent period, so acting on it now would mean
        trading on a relationship that has already largely decayed away, the same
        McLean-Pontiff logic already applied to Growth's asset_growth_yoy elsewhere in this
        file. Correctly left as originally designed; this sub-question is closed (won't flip).

        INDEPENDENTLY RE-VERIFIED 2026-08-25 (same "dig in, be certain" pass that corrected
        Stability's max_drawdown_1y sub-period numbers and Value's PE-vs-PB/PS claim, both of
        which had overstated an already-in-file finding). This one reproduced closely on a
        from-scratch re-run: full sample t=-1.83, first half t=-1.97, second half t=-0.44,
        terciles -1.58/-1.73/+0.52 - all within a few hundredths to a few tenths of the
        numbers above, not the several-point gap found in the other two claims. Confidence in
        this specific finding is high; the conclusion (won't flip) stands unchanged.

        BANK MOMENTUM MIRROR ADDED THEN REVERTED (2026-09-12, same day) - a fix mirrored
        (100-score) this pillar's final output for DEPOSITORY_BANK_INDUSTRIES symbols, citing
        a Fama-MacBeth panel where all 8 momentum-construction inputs came back significant
        and negative univariately. Reverted same day on closer inspection: the MULTIVARIATE
        version of that same panel (the correct spec once inputs are this collinear - see the
        OPEN QUESTION note above, which already documented mom_12m/rsi_14/macd_sign/
        price_vs_sma_* as severely collinear for the whole universe and explicitly warned
        "extracting weights from an unstable collinear regression would just encode noise")
        showed only ONE of the 8 factors (price_vs_sma_50, t=-2.43, small coefficient) survived
        jointly - the other 7 were statistically indistinguishable from zero once you control
        for the others, and rsi_14 flipped sign. "8 factors all significant and negative" was
        really one weak effect measured 8 different ways, not independent confirmation, and did
        not remotely support a full 100-score sign-flip. The panel also structurally excludes
        every bank that failed/delisted (SVB, Signature, First Republic - zero price_daily
        rows), so it never observed the tail case a momentum-inversion rule would most need to
        get right. Left unmirrored pending a redo that (1) uses the multivariate/consolidated
        spec, not univariate-per-factor, and (2) sizes any adjustment to the actual surviving
        effect instead of a full flip. See
        bank_momentum_mirror_reverted_univariate_fdr_collinearity_trap_20260912 in memory for
        the full writeup of this failure mode (it generalizes beyond Momentum).

        RETURN TYPES (STRICT):
        - metrics available with ≥1 scoreable field → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - all fields None → returns marker dict with reason="no_momentum_scores_computed"

        ERROR HANDLING:
        - Weak price-return momentum (±3%) → returns None for that timeframe (insufficient signal)
        - Missing historical prices → timeframe momentum is None (not guessed)

        MINIMUM DATA REQUIREMENT: At least one of 1m/3m/6m/12m momentum, RSI, MACD, or ROC must be
        available (not None). If everything is None/missing, returns data_unavailable marker.
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Returning data_unavailable marker for momentum_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_momentum_metrics_data"}

        # Named weights (2026-08-25 redesign, see docstring): momentum_1m dropped as a
        # standalone scored timeframe - standard academic 12-1 momentum construction
        # (Jegadeesh 1990) deliberately excludes the most recent month's raw return. Our own
        # panel confirmed why: trailing-1m return vs forward-1m return showed Spearman=-0.031
        # (p=4.2e-97, short-term reversal), but a double sort controlling for 12-1 momentum
        # showed the reversal is concentrated almost entirely in low-momentum (losing) names
        # (-0.31 spread) while high-momentum names showed continuation instead (+0.39 spread) -
        # a flat weighted-sum score can't encode that interaction, so the conservative fix is
        # dropping the most-recent-month return as its own scored input. momentum_1m is still
        # read below (see mom_12_1 derivation) - as an input to the 12-1 construction Jegadeesh
        # 1990 actually specifies, not as a standalone score.
        # UNIFORM EQUAL-WEIGHT (2026-09-11, user directive - see pillar_weights.py's
        # BASE_PILLAR_WEIGHTS comment for the full rationale): the 20/35/37/8 magnitude-tuned
        # split below traced to the same isolated-backtest/contaminated-FM-data family that
        # forced Growth and Value off similar weighting. All 4 slots (momentum_3m, mom_12_1,
        # averaged RSI/MACD, averaged SMA50/200) were flattened to 25% each - the RSI+MACD and
        # SMA50+SMA200 averaging (a redundancy/multicollinearity fix, not a weighting choice)
        # and the mom_12_1 Jegadeesh construction are unchanged. Historical reasoning below is
        # kept as audit trail.
        #
        # MOM_12_1 RE-EMPHASIZED, TECH_TREND DEMOTED (2026-09-14, goal session: "get factor
        # scores more in line with industry"). NOT another internal FM re-derivation of this
        # pillar's own noisy, severely-collinear panel (that's the exact trap the
        # "OPEN QUESTION"/"CONFIRMATORY RE-RUN" docstring notes above already warn against -
        # "extracting weights from an unstable collinear regression would just encode noise").
        # Grounded instead in real-world convergent evidence, the same evidentiary class
        # already used for Quality's margin_volatility reweight (loaders/helpers/
        # vqg_quality_score.py): every major institutional/academic Momentum factor definition
        # this repo could check - Jegadeesh & Titman (1993), Carhart's UMD factor (1997), AQR's
        # published momentum series, MSCI Momentum Index, S&P Momentum Index - is constructed
        # from a price-return lookback window (typically 12-1 or 6-1 month, sometimes
        # risk-adjusted), NEVER from RSI/MACD/SMA-crossover technical-analysis indicators. This
        # pillar's own `tech_trend` slot (RSI+MACD averaged) is not a weaker version of the same
        # factor - by every convergent institutional definition, it isn't the same factor at
        # all. This distinction is independent of and additional to this file's own already-
        # documented internal findings on tech_trend specifically: RSI's real (Wilder 1978)
        # signal is mean-reverting (higher RSI -> weakly LOWER forward return, opposite of this
        # pillar's trend-following "higher RSI = more bullish" treatment - see "RSI SIGN
        # QUESTION" docstring note above, decaying but real in 3 of 4 sub-samples), and
        # macd_sign's coefficient literally flips sign between univariate and multivariate specs
        # (severe collinearity, see "OPEN QUESTION" note) - the weakest evidentiary standing of
        # the pillar's 4 slots by this file's own analysis, not just by outside convention.
        # mom_12_1 raised 25->45 (the industry-standard core construction, and nominally the
        # strongest of the four return-window factors in this repo's own 2026-08-25 univariate
        # re-run, t=1.04 vs the others' 0.38-0.88 - suggestive not conclusive alone, but
        # consistent with rather than contradicting the industry-consensus case). tech_trend cut
        # 25->15 (weakest standing on both counts above). momentum_3m/sma_avg left closer to
        # their prior weight (25->20 each) - real trend-following/short-horizon literature
        # exists for both (Moskowitz/Ooi/Pedersen 2012 time-series momentum for SMA-style
        # trend-following; AQR's own momentum construction blends multiple horizons), and this
        # pillar's own IC validation (algo/research/per_component_ic_validation_20260911.py,
        # re-run 2026-09-14) found sma_avg's holdout t=2.78 - the best of the 3 non-mom_12_1
        # slots, better than momentum_3m's own 1.52 - so demoting it further than momentum_3m
        # would contradict this repo's own data, not just outside convention. Conservative
        # relative to what a literal single-factor Carhart/MSCI definition would imply (100% on
        # mom_12_1 alone) - this repo's standing practice per pillar_weights.py's governance
        # policy is to move deliberately, not to the point estimate, matching e.g. margin_
        # volatility landing at AQR's 25% rather than MSCI's ~33%.
        # WEIGHTS REBALANCED 2026-09-15 (user directive: "do what is needed so we get ours
        # like theirs", after live-verifying against fresh MTUM daily holdings). This
        # docstring's own 2026-09-14 note already found, from real institutional/academic
        # literature alone, that momentum_3m/tech_trend/sma_avg aren't part of any convergent
        # Momentum factor definition (Jegadeesh-Titman, Carhart UMD, AQR, MSCI, S&P all
        # construct purely from risk-adjusted return-lookback windows, never RSI/MACD/SMA) -
        # but stopped short of the literal 100%-on-lookback-windows point estimate as a
        # deliberate, documented conservative choice. Fresh empirical test against real MTUM
        # closes that gap: cap-neutral Spearman rank correlation (controlling for market cap,
        # so it reflects real factor agreement, not company size) was 0.186-0.240 for the
        # then-current 45/20/15/20 blend, but 0.564 using ONLY risk-adjusted 6m + 12-1 month
        # momentum (50/50, matching MSCI's own published "looking at both 6- and 12-month
        # holding period returns... using modified Sharpe ratios" description exactly) -
        # every tested configuration that added momentum_3m/tech_trend/sma_avg back in
        # monotonically hurt the correlation, never helped. momentum_3m/RSI/MACD/SMA-position
        # remain fetched/persisted/displayed (informational, not scored - same convention
        # already used elsewhere in this codebase for demoted fields) - just no longer part
        # of momentum_score itself.
        weights = {
            "momentum_6m": 0.50,
        }

        vol_252d = metrics.get("vol_252d")
        median_vol_252d = self._get_median_vol_252d()
        min_mult, max_mult = self._get_risk_adjustment_multiplier_bounds()

        weighted_sum = 0.0
        total_weight = 0.0
        for key, w in weights.items():
            if metrics.get(key) is not None:
                score = self._pct_to_score(
                    self._risk_adjust_pct(metrics[key], vol_252d, median_vol_252d, min_mult, max_mult)
                )
                if score is not None:  # Skip weak momentum (score=None)
                    weighted_sum += score * w
                    total_weight += w

        # 12-1 momentum (skip most-recent-month, Jegadeesh 1990 standard construction) -
        # REPLACES raw momentum_6m/momentum_12m 2026-08-25 (see docstring RESOLVED note).
        # Derived rather than requiring a new stored field: cumulative return from 12mo-ago to
        # 1mo-ago is algebraically (1+momentum_12m/100)/(1+momentum_1m/100) - 1, converted back
        # to a percentage number to match _pct_to_score's expected input convention. Guarded
        # against a near-zero denominator (would require momentum_1m ~ -100%, a stock price
        # going to ~zero in a month - not realistic for a scoreable position, but NaN/Infinity
        # guarded both directions per this codebase's standard convention regardless).
        mom_12m_raw = metrics.get("momentum_12m")
        mom_1m_raw = metrics.get("momentum_1m")
        if mom_12m_raw is not None and mom_1m_raw is not None:
            denom = 1.0 + mom_1m_raw / 100.0
            if abs(denom) > 1e-6:
                mom_12_1 = ((1.0 + mom_12m_raw / 100.0) / denom - 1.0) * 100.0
                if math.isfinite(mom_12_1):
                    mom_12_1_score = self._pct_to_score(
                        self._risk_adjust_pct(mom_12_1, vol_252d, median_vol_252d, min_mult, max_mult)
                    )
                    if mom_12_1_score is not None:  # Skip weak momentum (score=None)
                        weighted_sum += mom_12_1_score * 0.50
                        total_weight += 0.50

        # RSI(14) + MACD sign, CONSOLIDATED (see CONSOLIDATED 2026-08-28 docstring note):
        # averaged into one "technical trend confirmation" slot, combined weight 0.37
        # (21%+16%, unchanged), same self-normalizing "average what's available, don't
        # double-weight correlated inputs" treatment this pillar already gives SMA-50/200
        # below and Risk gives its volatility windows.
        #
        # RSI(14): momentum-following curve (not mean-reversion) - higher RSI is more
        # bullish, with only a slight pullback at extreme overbought (>85) for reversal risk.
        #
        # MACD: sign only, not magnitude. MACD's raw value scales with the stock's price
        # level (a MACD of 2 means something different for a $10 stock vs a $500 stock), so
        # magnitude isn't comparable across symbols - use it purely as a bull/bear trend
        # confirmation signal.
        #
        # FIX 2026-08-18 (loader-health review, log-noise sweep): a prior commit speculatively
        # preferred a "macd_line" field, anticipating a migration that never actually happened
        # on this table - _prepare_batch_context()'s own query (~line 402-406) selects
        # "rsi_14, macd, sma_50, sma_200, close" from technical_data_daily and nothing else,
        # so metrics.get("macd_line") was provably always None, 100% of the time, for every
        # symbol, every run. (technical_data_daily has no macd_line column at all - a
        # same-named column DOES exist, but on a different table, momentum_metrics, added by
        # an unrelated migration 119 - not the same computation, not queried here.) The
        # resulting "legacy field" warning fired on ~4926/4930 symbols every single
        # stock_scores run - not a rare backward-compat path, pure log noise masking real
        # warnings, with zero effect on the actual score (this WAS already the only value
        # ever used). Reverted to using "macd" directly.
        # tech_trend (RSI+MACD) DEMOTED TO INFORMATIONAL-ONLY 2026-09-15 - see WEIGHTS
        # REBALANCED note above. No longer scored; raw rsi_14/macd values remain exposed via
        # the API response's own top-level fields for display, unaffected by this removal.

        # ROC (Rate of Change) composite REMOVED 2026-08-25 (goal: full scoring-architecture
        # audit): roc_20d/60d/120d/252d are literally the same computation as
        # momentum_1m/3m/6m/12m above (both `close.pct_change()` over near-identical trading-
        # day windows - momentum_1m uses 21 trading days back vs roc_20d's 20, momentum_12m
        # and roc_252d both use exactly 252) - this wasn't a diversifying signal, it was the
        # same four numbers counted a second time. Removed rather than reweighted.

        # sma_avg (price_vs_sma_50/200) DEMOTED TO INFORMATIONAL-ONLY 2026-09-15 - see WEIGHTS
        # REBALANCED note above. No longer scored; raw price_vs_sma_50/200 values remain
        # exposed via the API response's own top-level fields for display.

        if total_weight >= MOMENTUM_MIN_WEIGHT:
            return weighted_sum / total_weight
        if total_weight > 0:
            logger.debug(
                f"[STOCK_SCORES] Returning data_unavailable marker for momentum_score({symbol}) - "
                f"only {total_weight:.2f} weight available, below MOMENTUM_MIN_WEIGHT={MOMENTUM_MIN_WEIGHT}. "
                f"See that constant's docstring - a thin fragment of the pillar isn't a confident score."
            )
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": "insufficient_momentum_inputs_thin_sample",
            }
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for momentum_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_momentum_scores_computed"}

    def _get_median_vol_252d(self) -> float:
        """Batch-computed median volatility_252d across self._stability_cache (recomputed fresh
        on every scoring run, not frozen - see MEDIAN_UNIVERSE_VOL_252D's own FROZEN-CONSTANT
        DRIFT docstring note for why a snapshot constant would go stale). Falls back to that
        live-measured constant when _stability_cache is empty/unpopulated (isolated unit tests
        that never run `_prepare_batch_context`, or a genuinely empty batch) - same graceful-
        degradation convention this pillar already uses everywhere else. Cached on the instance
        after first computation - the batch doesn't change mid-run, so recomputing per-symbol
        would be wasted work across thousands of calls.
        """
        cached: float | None = getattr(self, "_median_vol_252d_cache", None)
        if cached is not None:
            return cached
        stability_cache = getattr(self, "_stability_cache", None)
        vols = sorted(
            float(row[0])
            for row in (stability_cache or {}).values()
            if row and row[0] is not None and float(row[0]) > 0
        )
        median = vols[len(vols) // 2] if vols else MEDIAN_UNIVERSE_VOL_252D
        self._median_vol_252d_cache = median
        return median

    def _get_risk_adjustment_multiplier_bounds(self) -> tuple[float, float]:
        """Batch-computed [1st, 99th] percentile of median_vol_252d/vol_252d across
        self._stability_cache - see MAX_RISK_ADJUSTMENT_MULTIPLIER's own docstring for why this
        replaced a hardcoded [0.5x, 2.0x]. Same _percentile() interpolation as
        factor_normalization.py's `_winsorize_group`, and the same <5-symbols "too few peers to
        trust a percentile from" fallback to the static constants - not just an empty-cache
        fallback, an actual replay of that helper's own threshold.
        """
        cached: tuple[float, float] | None = getattr(self, "_risk_adjustment_multiplier_bounds_cache", None)
        if cached is not None:
            return cached
        stability_cache = getattr(self, "_stability_cache", None)
        median_vol_252d = self._get_median_vol_252d()
        ratios = sorted(
            median_vol_252d / float(row[0])
            for row in (stability_cache or {}).values()
            if row and row[0] is not None and float(row[0]) >= MIN_VOL_252D_FOR_RISK_ADJUSTMENT
        )
        n = len(ratios)
        if n < 5:
            bounds = (MIN_RISK_ADJUSTMENT_MULTIPLIER, MAX_RISK_ADJUSTMENT_MULTIPLIER)
        else:

            def _percentile(pct: float) -> float:
                rank = pct / 100.0 * (n - 1)
                lo = int(rank)
                hi = min(lo + 1, n - 1)
                frac = rank - lo
                return ratios[lo] + (ratios[hi] - ratios[lo]) * frac

            bounds = (_percentile(1.0), _percentile(99.0))
        self._risk_adjustment_multiplier_bounds_cache = bounds
        return bounds

    @staticmethod
    def _risk_adjust_pct(
        raw_pct: float,
        vol_252d: float | None,
        median_vol_252d: float = MEDIAN_UNIVERSE_VOL_252D,
        min_multiplier: float = MIN_RISK_ADJUSTMENT_MULTIPLIER,
        max_multiplier: float = MAX_RISK_ADJUSTMENT_MULTIPLIER,
    ) -> float:
        """Risk-adjust a raw percentage return for feeding into `_pct_to_score` - see
        RISK-ADJUSTED MOMENTUM module-level docstring for the full rationale. Returns raw_pct
        unchanged when vol_252d is missing or below MIN_VOL_252D_FOR_RISK_ADJUSTMENT (graceful
        degradation, same "score what's available" convention as every other input in this
        pillar - a missing/unreliable volatility reading isn't a reason to withhold the
        momentum reading itself).

        median_vol_252d/min_multiplier/max_multiplier default to the frozen module constants
        (kept for direct unit testing of this method in isolation) - `_score_momentum` always
        passes the freshly-computed `_get_median_vol_252d()`/`_get_risk_adjustment_multiplier_
        bounds()` values instead, per those methods' own docstrings.
        """
        if vol_252d is None or vol_252d < MIN_VOL_252D_FOR_RISK_ADJUSTMENT:
            return raw_pct
        multiplier = median_vol_252d / vol_252d
        multiplier = max(min_multiplier, min(max_multiplier, multiplier))
        return raw_pct * multiplier

    @staticmethod
    def _pct_to_score(pct_return: float) -> float | None:
        """Convert percentage return to 0-100 score.

        Returns None if momentum is weak (< ±3%), as this indicates
        insufficient conviction. Fail-fast: weak signal is missing data, not low score.
        -20% = 0, ±3% = None, +20% = 100.

        pct_return is a percentage NUMBER (e.g. 20.0 for +20%), not a fraction - matches
        load_risk_metrics_daily.py's ret_pct = (price_new - price_old) / price_old * 100,
        which is what momentum_1m/3m/6m/12m are computed as and stored as.
        """
        # Weak momentum zone: -3% to +3% lacks conviction. This previously checked
        # -0.03 <= pct_return <= 0.03 - a threshold 100x too small for the percentage-number
        # scale pct_return is actually on, so it matched essentially no real momentum value
        # (typical 1m/3m/6m/12m returns are single-to-double-digit percent) and this weak-
        # signal exclusion never fired in practice - every momentum reading, however weak,
        # was scored instead of being excluded as insufficient conviction per the documented
        # design intent.
        if -3 <= pct_return <= 3:
            return None

        # Map momentum: -20% = 0, +20% = 100
        score = 50 + (pct_return / 0.4)
        return max(0, min(100, score))

    @staticmethod
    def _rsi_to_score(rsi: float) -> float:
        """Map RSI(14) to a momentum-following 0-100 score (higher RSI = more bullish).

        This is deliberately NOT a mean-reversion mapping (which would penalize high RSI as
        "overbought"). For a momentum factor, sustained strength (RSI 50-85) should score
        well; only extreme overbought (>85) gets a mild pullback for reversal risk.
        """
        rsi = max(0.0, min(100.0, rsi))
        if rsi <= 30:
            return (rsi / 30) * 30
        if rsi <= 50:
            return 30 + ((rsi - 30) / 20) * 20
        if rsi <= 70:
            return 50 + ((rsi - 50) / 20) * 35
        if rsi <= 85:
            return 85 + ((rsi - 70) / 15) * 15
        return max(60.0, 100 - (rsi - 85) * 3)

    @staticmethod
    def _components_with_corrected_momentum(components_old: Any, momentum_score_new: float | None) -> str:
        """Return components (the Pass-1 JSON breakdown dict) re-serialized with its 'momentum'
        key set to momentum_score_new, every other pillar untouched. Mirrors
        ValueMetricsMixin._components_with_corrected_value / GrowthScoringMixin.
        _components_with_corrected_growth / RiskScoringMixin._components_with_corrected_risk
        exactly - same pattern, this pillar's key."""
        if isinstance(components_old, dict):
            components_new = dict(components_old)
        elif components_old:
            components_new = json.loads(components_old)
        else:
            components_new = {}
        components_new["momentum"] = momentum_score_new
        return json.dumps(components_new)

    def _recompute_momentum_score_for_row(
        self,
        symbol: str,
        m3_raw: Any,
        rsi_14: Any,
        macd: Any,
        sma_50: Any,
        sma_200: Any,
        close: Any,
        vol: float | None,
        median_vol_252d: float,
        min_mult: float,
        max_mult: float,
        mom_12_1_pct: dict[str, float],
        mom_6m_pct: dict[str, float],
    ) -> float | None:
        """Recompute a single symbol's full momentum_score for
        update_momentum_sector_relative_mom_12_1() - split out purely to keep that method's
        cyclomatic complexity within this repo's ruff C901 bound. Same weights/gate as
        `_score_momentum`'s 2026-09-15 WEIGHTS REBALANCED note: mom_6m 50% + mom_12_1 50%
        (both from the pre-computed universe-wide pct maps), momentum_3m/tech_trend/sma_avg
        no longer scored (m3_raw/rsi_14/macd/sma_50/sma_200/close params kept for call-site
        stability - StockScoreAccordion/other callers still pass them - just unused for
        scoring now).
        """
        weighted_sum = 0.0
        total_weight = 0.0

        if symbol in mom_6m_pct:
            weighted_sum += mom_6m_pct[symbol] * 0.50
            total_weight += 0.50

        if symbol in mom_12_1_pct:
            weighted_sum += mom_12_1_pct[symbol] * 0.50
            total_weight += 0.50

        if total_weight >= MOMENTUM_MIN_WEIGHT:
            return round(weighted_sum / total_weight, 2)
        if total_weight > 0:
            logger.debug(
                f"[STOCK_SCORES] {symbol} momentum_score withheld in sector-relative pass: "
                f"only {total_weight:.2f} weight available, below MOMENTUM_MIN_WEIGHT="
                f"{MOMENTUM_MIN_WEIGHT}."
            )
        return None

    @staticmethod
    def _recompute_composite_for_row(
        quality_score: Any, growth_score: Any, value_score: Any, risk_score: Any, momentum_score_new: float | None
    ) -> tuple[float, float]:
        """Recompute composite_score + data_completeness for one row, given the pillar scores
        as they currently stand plus the new momentum_score - split out purely to keep
        update_momentum_sector_relative_mom_12_1()'s complexity within this repo's ruff C901
        bound, no behavior change. Mirrors update_growth_sector_neutral_scores()'s identical
        inline block exactly."""
        risk_score_float = float(risk_score) if risk_score is not None else None
        weights = _value_risk_adjusted_weights(risk_score_float)
        composite_val = 0.0
        for pillar_name, pillar_score in (
            ("quality", quality_score),
            ("growth", growth_score),
            ("value", value_score),
            ("risk", risk_score),
            ("momentum", momentum_score_new),
        ):
            if pillar_score is not None:
                composite_val += float(pillar_score) * weights[pillar_name]
        composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)

        all_scores_new: dict[str, float | None] = {
            "quality": float(quality_score) if quality_score is not None else None,
            "growth": float(growth_score) if growth_score is not None else None,
            "value": float(value_score) if value_score is not None else None,
            "risk": float(risk_score) if risk_score is not None else None,
            "momentum": momentum_score_new,
        }
        available_weight = sum(
            BASE_PILLAR_WEIGHTS[pillar] for pillar, score in all_scores_new.items() if score is not None
        )
        data_completeness_new = min(99.99, round(available_weight * 100, 2))
        return composite_score_new, data_completeness_new

    def update_momentum_sector_relative_mom_12_1(self) -> None:
        """Batch pass: replace mom_12_1's Pass-1 PROVISIONAL absolute-curve score (raw
        risk-adjusted return fed through `_pct_to_score`'s fixed +-20%-saturation curve, same
        for every sector) with a true sector-relative z-score against the current run's
        universe, then FULLY RECOMPUTE momentum_score/composite_score from scratch - mirrors
        `update_growth_sector_neutral_scores()`'s pure-overwrite pattern (loaders/stock_scores/
        growth_scoring.py) exactly, which itself mirrors Quality's.

        TWO-LAYER VALIDATION POLICY (2026-09-15, user directive - see pillar_weights.py's own
        "TWO-LAYER VALIDATION POLICY" comment block): this is scoped ONLY to mom_12_1 (45% of
        momentum_score, the literature-standard Jegadeesh 1990 construction and the single
        input a real institutional Momentum index actually sector-relative-z-scores) - NOT
        momentum_3m (no comparable real-index precedent found), NOT tech_trend/sma_avg (RSI is
        already a bounded oscillator, MACD sign-only, SMA already self-relative to that stock's
        own moving average - none of these are cross-sectional return comparisons a sector peer
        group would even apply to). Directly supersedes the evidentiary basis behind
        `momentum_pillar_sector_relative_mom_12_1_rejected_20260911` (memory) / the 2026-09-11
        revert (`6666ff0f4`) of the equivalent earlier attempt (`cc4030f8a`) - that rejection
        tested mom_12_1's own standalone forward-return IC (universe-wide beat sector-relative,
        0.0437 vs 0.0383 pooled Spearman IC, both eras) and concluded sector-relative was worse.
        Under the new policy that was the wrong bar for a PILLAR-level construction choice: the
        pillar's job is to accurately MEASURE the real momentum factor, not to independently
        predict returns (only composite_score is validated on that basis) - and MTUM's actual
        underlying index (MSCI USA Momentum **SR** "Sector-Relative" Variant, confirmed via two
        independent primary-source methodology-PDF extractions 2026-09-15) z-scores momentum
        WITHIN each GICS sector before combining. Live-verified this actually closes real
        alignment gap: full-universe capband overlap vs real MTUM/XMMO/DWAS top-25 went from
        1/25 (large-cap) / 1/25 (mid) / 0/25 (small) under the pre-existing universe-wide
        risk-adjusted construction to 6/25 / 4/25 / 6/25 under this sector-relative version,
        computed fresh via `_score_momentum` directly (dry run, no DB writes, before this
        method existed) - same methodology already used to validate Quality/Growth/Value's own
        sector-relative rewrites against real fund holdings.

        FPI PEER-GROUP SPLIT: `sector_neutral_zscore` already carries the FPI peer-group split
        (2026-09-14 fix, same module) - this pass gets that split for free, which should also
        help the FPI-overrepresentation pattern independently found in Momentum's current top-25
        lists (10/25, 7/25, 11/25 FPI vs a 14.9-19.2% band base rate) without any extra code here.

        MECHANISM: risk-adjust each symbol's raw mom_12_1 return via the existing
        `_risk_adjust_pct` (unchanged - the risk-adjustment and the sector-relative step are
        independent corrections, composed risk-adjust-then-sector-z: normalize for the stock's
        OWN idiosyncratic volatility first, then compare that risk-adjusted return within its
        sector peer group), then `sector_neutral_zscore`/`zscore_to_percentile_scale`
        (loaders/helpers/factor_normalization.py, same primitive Quality/Growth/Value already
        use) in place of `_pct_to_score`'s fixed curve. momentum_3m/tech_trend/sma_avg are
        recomputed identically to `_score_momentum` (same weights, same MOMENTUM_MIN_WEIGHT
        gate) so this pass is a full, consistent momentum_score recompute, not a partial patch
        - same reason Quality/Growth's sector-neutral passes fully recompute rather than patch
        one component (only the final blended score is stored, not per-component sub-scores).

        INVESTABILITY FLOOR: same $300M algo_config.min_market_cap_millions floor as every
        other sector-neutral pass - sub-floor nanocaps distort the peer-group percentile
        boundaries real, investable companies get ranked against; those symbols simply aren't
        included here and keep whatever Pass-1 already gave them.

        Composite_score recomputed exactly as update_growth_sector_neutral_scores recomputes
        it - from quality_score/value_score/risk_score/growth_score as they currently stand
        (untouched by this pass) plus the new momentum_score, via `_value_risk_adjusted_weights`.
        Must run BEFORE update_rs_percentiles() (rs_percentile should rank the FINAL
        momentum_score, not Pass-1's provisional one) and AFTER
        update_growth_sector_neutral_scores() (so this pass's own composite recompute sees
        Growth's already-finalized growth_score) - same "later pass sees earlier pass's
        finalized pillar" ordering already established for Value/Growth in post_run().

        Raises on failure, same as every other post_run() batch pass - an inconsistent
        momentum_score/composite_score is a live-trading-relevant correctness issue.
        """
        try:
            with _owner().DatabaseContext("write") as cur:
                # ACTIVE-UNIVERSE GUARD + INVESTABILITY FLOOR: same pattern as every sibling
                # sector-neutral pass (Quality/Growth) - see their own docstrings for the full
                # evidence trail on why each guard exists.
                cur.execute(
                    """
                    SELECT ss.symbol, ss.momentum_score, ss.composite_score, ss.quality_score,
                           ss.growth_score, ss.value_score, ss.risk_score, ss.components,
                           ss.data_completeness, ss.data_unavailable,
                           mm.momentum_1m, mm.momentum_3m, mm.momentum_12m,
                           td.rsi_14, td.macd, td.sma_50, td.sma_200, td.close,
                           sm.volatility_252d, cp.sector, COALESCE(cis.is_foreign_private_issuer, false),
                           mm.momentum_6m
                    FROM stock_scores ss
                    JOIN momentum_metrics mm ON mm.symbol = ss.symbol
                    JOIN value_metrics vm ON vm.symbol = ss.symbol
                    JOIN stock_symbols su ON su.symbol = ss.symbol
                    LEFT JOIN company_profile cp ON cp.symbol = ss.symbol
                    LEFT JOIN company_info_sec cis ON cis.symbol = ss.symbol
                    LEFT JOIN stability_metrics sm ON sm.symbol = ss.symbol
                    LEFT JOIN LATERAL (
                        SELECT rsi_14, macd, sma_50, sma_200, close FROM technical_data_daily
                        WHERE symbol = ss.symbol ORDER BY date DESC LIMIT 1
                    ) td ON true
                    WHERE ss.momentum_score IS NOT NULL
                      AND COALESCE(mm.data_unavailable, false) = false
                      AND vm.market_cap >= %s
                      AND ("""
                    + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                    + ")",
                    (getattr(self, "_min_investable_market_cap", None) or DEFAULT_MIN_INVESTABLE_MARKET_CAP,),
                )
                rows = cur.fetchall()

            if not rows:
                logger.warning(
                    "[STOCK_SCORES] update_momentum_sector_relative_mom_12_1: no eligible rows found - skipping."
                )
                return

            # Median vol_252d for this batch (same convention as _get_median_vol_252d, computed
            # fresh here since this pass runs off its own dedicated query, not self._stability_cache).
            vols = sorted(float(row[18]) for row in rows if row[18] is not None and float(row[18]) > 0)
            median_vol_252d = vols[len(vols) // 2] if vols else MEDIAN_UNIVERSE_VOL_252D

            # Dynamic risk-adjustment multiplier bounds ([1st,99th] percentile of median_vol/
            # vol_252d across THIS pass's own row set) - same algorithm as
            # _get_risk_adjustment_multiplier_bounds(), replicated locally rather than called
            # directly: that method reads self._stability_cache (Pass 1's population), which
            # this pass never populates (it runs off its own separately-queried, differently-
            # filtered row set with a different median_vol_252d baseline) - calling it as-is
            # would clip against bounds derived from a population this pass doesn't actually
            # use. Keeps Pass 1 and this pass internally consistent with EACH OTHER'S OWN
            # population, not silently falling back to the static [0.5x,2.0x] constants by
            # omission (caught in review before this landed).
            ratios = sorted(
                median_vol_252d / float(row[18])
                for row in rows
                if row[18] is not None and float(row[18]) >= MIN_VOL_252D_FOR_RISK_ADJUSTMENT
            )
            n_ratios = len(ratios)
            if n_ratios < 5:
                min_mult, max_mult = MIN_RISK_ADJUSTMENT_MULTIPLIER, MAX_RISK_ADJUSTMENT_MULTIPLIER
            else:

                def _percentile(pct: float, _ratios: list[float] = ratios, _n: int = n_ratios) -> float:
                    rank = pct / 100.0 * (_n - 1)
                    lo = int(rank)
                    hi = min(lo + 1, _n - 1)
                    frac = rank - lo
                    return _ratios[lo] + (_ratios[hi] - _ratios[lo]) * frac

                min_mult, max_mult = _percentile(1.0), _percentile(99.0)

            # Risk-adjust each symbol's raw mom_12_1 (skip-month construction) and mom_6m, same
            # derivation as _score_momentum's inline version. Both fed into the same
            # universe-wide z-score treatment and blended 50/50 (see WEIGHTS REBALANCED note
            # on _score_momentum above for the full evidence trail - fresh MTUM validation,
            # not internal IC alone).
            mom_12_1_risk_adj: dict[str, float] = {}
            mom_6m_risk_adj: dict[str, float] = {}
            for row in rows:
                symbol, m1_raw, m12_raw, vol252, m6_raw = row[0], row[10], row[12], row[18], row[21]
                vol = float(vol252) if vol252 is not None else None
                if m1_raw is not None and m12_raw is not None:
                    m1f, m12f = float(m1_raw), float(m12_raw)
                    denom = 1.0 + m1f / 100.0
                    if abs(denom) > 1e-6:
                        mom_12_1 = ((1.0 + m12f / 100.0) / denom - 1.0) * 100.0
                        if math.isfinite(mom_12_1):
                            mom_12_1_risk_adj[symbol] = self._risk_adjust_pct(
                                mom_12_1, vol, median_vol_252d, min_mult, max_mult
                            )
                if m6_raw is not None:
                    mom_6m_risk_adj[symbol] = self._risk_adjust_pct(
                        float(m6_raw), vol, median_vol_252d, min_mult, max_mult
                    )

            # UNIVERSE-WIDE, not sector-relative (fixed 2026-09-15 - see this module's own
            # update_momentum_sector_relative_mom_12_1 docstring and universe_wide_zscore's
            # docstring in factor_normalization.py for the full evidence trail: sector-relative
            # z-scoring was based on a misread of MTUM's real methodology - "sector
            # diversification" there is a portfolio-construction-level exposure CAP, not a
            # stock-scoring-level per-sector z-score - and empirically halved cap-neutral rank
            # correlation vs fresh MTUM holdings, 0.235 vs 0.558 universe-wide).
            mom_12_1_pct = zscore_to_percentile_scale(universe_wide_zscore(mom_12_1_risk_adj))
            mom_6m_pct = zscore_to_percentile_scale(universe_wide_zscore(mom_6m_risk_adj))
            logger.info(
                f"[STOCK_SCORES] Momentum universe-wide mom_12_1 z-score ({len(mom_12_1_pct)}/{len(rows)} scored), "
                f"mom_6m z-score ({len(mom_6m_pct)}/{len(rows)} scored)"
            )

            min_completeness_threshold = getattr(self, "_min_completeness_threshold", 70.0)

            updates: list[tuple[str, float | None, float, str | None, float, bool]] = []
            for row in rows:
                (
                    symbol,
                    momentum_score_old,
                    composite_score_old,
                    quality_score,
                    growth_score,
                    value_score,
                    risk_score,
                    components_old,
                    data_completeness_old,
                    data_unavailable_old,
                    _m1_raw,
                    m3_raw,
                    _m12_raw,
                    rsi_14,
                    macd,
                    sma_50,
                    sma_200,
                    close,
                    vol252,
                    _sector,
                    _is_fpi,
                    _m6_raw,
                ) = row
                vol = float(vol252) if vol252 is not None else None

                momentum_score_new = self._recompute_momentum_score_for_row(
                    symbol,
                    m3_raw,
                    rsi_14,
                    macd,
                    sma_50,
                    sma_200,
                    close,
                    vol,
                    median_vol_252d,
                    min_mult,
                    max_mult,
                    mom_12_1_pct,
                    mom_6m_pct,
                )
                composite_score_new, data_completeness_new = self._recompute_composite_for_row(
                    quality_score, growth_score, value_score, risk_score, momentum_score_new
                )
                data_unavailable_new = data_completeness_new < min_completeness_threshold

                momentum_score_old_f = float(momentum_score_old) if momentum_score_old is not None else None
                if (
                    momentum_score_new != momentum_score_old_f
                    or composite_score_new != float(composite_score_old)
                    or data_completeness_new
                    != (float(data_completeness_old) if data_completeness_old is not None else None)
                    or data_unavailable_new != bool(data_unavailable_old)
                ):
                    components_json = self._components_with_corrected_momentum(components_old, momentum_score_new)
                    updates.append(
                        (
                            symbol,
                            momentum_score_new,
                            composite_score_new,
                            components_json,
                            data_completeness_new,
                            data_unavailable_new,
                        )
                    )

            if not updates:
                logger.info(
                    "[STOCK_SCORES] Momentum sector-relative mom_12_1 pass: no symbol's momentum_score/"
                    "composite_score changed."
                )
                return

            with _owner().DatabaseContext("write") as cur:
                _owner().execute_values(
                    cur,
                    """
                    UPDATE stock_scores AS ss
                    SET momentum_score = v.momentum_score,
                        composite_score = v.composite_score,
                        components = v.components::jsonb,
                        data_completeness = v.data_completeness,
                        data_unavailable = v.data_unavailable,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (VALUES %s) AS v(symbol, momentum_score, composite_score, components,
                                           data_completeness, data_unavailable)
                    WHERE ss.symbol = v.symbol
                    """,
                    updates,
                    template="(%s, %s, %s, %s, %s, %s)",
                )
            logger.info(
                f"[STOCK_SCORES] Momentum sector-relative mom_12_1 pass corrected "
                f"{len(updates)}/{len(rows)} symbols' momentum_score/composite_score (post_run completed)"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"Momentum sector-relative mom_12_1 batch update failed - stock scores cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def update_rs_percentiles(self) -> None:
        """Batch pass: rank all stocks by momentum_score and write true RS percentile.

        Uses PERCENT_RANK() so a stock scoring higher than 90% of peers gets rs_percentile=90.
        Must run after all per-symbol scores are loaded.

        GOVERNANCE: PostgreSQL sorts NULLs last by default, so ranking over the full table
        (including rows with no momentum_score) previously gave every NULL-momentum stock a
        false top-quintile rs_percentile (~81, the percentile of the last real row) instead
        of reflecting that the stock has no momentum data at all. That fabricated value fed
        straight into Phase 7's signal-generation completeness gate, defeating the exact
        check meant to catch missing data. Rank only over rows with real momentum_score, and
        explicitly null out rs_percentile for the rest so missing data stays visibly missing.

        CRITICAL: Raises on failure. RS percentiles are essential for ranking signal quality;
        missing or stale percentiles invalidate momentum-based signal filtering.

        CRITICAL FIX 2026-08-06: Update `updated_at` timestamp to ensure Phase 1's freshness
        check recognizes that post_run() completed successfully and rs_percentile was computed.
        Without this, rs_percentile stays NULL and Phase 7 filters out all signals.
        """
        try:
            with _owner().DatabaseContext("write") as cur:
                # ACTIVE-UNIVERSE GUARD (added 2026-09-09, migration 1276's own code fix - see
                # NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE's own module-level comment in
                # utils/loaders/helpers.py for the full evidence trail). All three UPDATEs below
                # previously ran over every stock_scores row unconditionally - a closed-end fund/
                # BDC/trust row that predates (or later drifted out of) the active-universe
                # exclusion get_active_symbols(exclude_etfs=True) enforces for the per-symbol
                # fetch path (a) polluted the PERCENT_RANK() ranking population real stocks are
                # scored against, (b) kept getting its own rs_percentile freshly computed, and
                # (c) kept getting updated_at bumped to look like a live, current-day score every
                # single run - the mechanism that let RGT/ASA/GGN/etc. resurface with a
                # fresh-looking updated_at despite the fetch path itself never writing them again.
                _active_universe_join = (
                    "JOIN stock_symbols su ON su.symbol = stock_scores.symbol "
                    "LEFT JOIN company_info_sec cis ON cis.symbol = stock_scores.symbol "
                    "WHERE stock_scores.momentum_score IS NOT NULL AND ("
                    + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                    + ")"
                )
                # First, update rs_percentile via PERCENT_RANK for symbols with momentum scores
                cur.execute(
                    """
                    UPDATE stock_scores ss
                    SET rs_percentile = ranked.pct,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (
                        SELECT stock_scores.symbol,
                               ROUND(
                                   (PERCENT_RANK() OVER (ORDER BY stock_scores.momentum_score))::NUMERIC * 100,
                                   2
                               ) AS pct
                        FROM stock_scores
                        """
                    + _active_universe_join
                    + """
                    ) ranked
                    WHERE ss.symbol = ranked.symbol
                """
                )
                # Second, explicitly null out rs_percentile for symbols without momentum scores
                # (original behavior, no join needed - also correctly covers a stock_scores row
                # for a symbol with no stock_symbols row at all, which the join-based branch
                # below can never reach).
                cur.execute("""
                    UPDATE stock_scores
                    SET rs_percentile = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE momentum_score IS NULL AND rs_percentile IS NOT NULL
                """)
                # Second-b, also null out rs_percentile for symbols that DO have a momentum_score
                # but no longer belong to the active, non-fund scored universe (the case the
                # original query never handled at all).
                cur.execute(
                    """
                    UPDATE stock_scores ss
                    SET rs_percentile = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    FROM stock_symbols su
                    LEFT JOIN company_info_sec cis ON cis.symbol = su.symbol
                    WHERE ss.symbol = su.symbol
                      AND ss.rs_percentile IS NOT NULL
                      AND ss.momentum_score IS NOT NULL
                      AND NOT ("""
                    + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                    + ")"
                )
                # Third, update timestamp for any remaining rows to mark post_run completion -
                # scoped to the same active universe so an excluded symbol's updated_at doesn't
                # get bumped to look like a fresh score on every run.
                cur.execute(
                    """
                    UPDATE stock_scores ss
                    SET updated_at = CURRENT_TIMESTAMP
                    FROM stock_symbols su
                    LEFT JOIN company_info_sec cis ON cis.symbol = su.symbol
                    WHERE ss.symbol = su.symbol
                      AND (ss.rs_percentile IS NOT NULL OR ss.momentum_score IS NOT NULL)
                      AND ("""
                    + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                    + ")"
                )
            logger.info("RS percentiles updated via batch rank (post_run completed)")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"RS percentile batch update failed - stock scores cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
