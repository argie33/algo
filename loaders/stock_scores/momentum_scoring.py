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
    DEFAULT_MIN_ADV_DOLLARS,
    DEFAULT_MIN_STOCK_PRICE,
    LIQUIDITY_FLOOR_JOIN_SQL,
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

# AQR MOMENTUM PIVOT (2026-09-17, /goal directive: "moving away from the msci and towards the
# aqr for the factors"). REPLACES the entire risk-adjusted-Sharpe-ratio / 6m+12-1 blend
# construction below (kept in git history, not here, per this repo's own "delete dead
# mechanisms rather than leave them inert" convention - see e.g. pillar_weights.py's
# VALUE_RISK_INTERACTION removal). Same pivot pattern already applied to Risk
# (risk_scoring.py's beta_bab, 2026-09-17): stop citing/approximating MSCI's published index
# methodology, replace with the actual academic AQR factor definition.
#
# AQR's momentum factor - Asness, Moskowitz & Pedersen (2013), "Value and Momentum Everywhere,"
# Journal of Finance 68(3), Section I.B, and consistently the same construction used in
# Jegadeesh & Titman (1993) and Carhart's UMD (1997) that AMP's paper builds on - is the
# cumulative RAW (not risk-adjusted, not vol-scaled) return from 12 months ago to 1 month ago
# (the "12-1" skip-month window), cross-sectionally ranked/z-scored. No Sharpe-ratio-style
# division by realized volatility, no blend with a separate 6-month window, no risk-free-rate
# netting - none of those appear anywhere in AMP's or Carhart's construction. Per this repo's
# TWO-LAYER VALIDATION POLICY (pillar_weights.py): a pillar-level construction is validated
# against fidelity to the real, sourced factor definition, not its own standalone IC - the
# MSCI-Sharpe construction's real MTUM-holdings validation (0.564 cap-neutral correlation,
# cited in this file's git history) was evidence FOR that MSCI-specific construction, not
# evidence against AQR's different, differently-defined factor; the two are answering different
# questions ("does this resemble MSCI's index" vs. "does this resemble AQR's factor"), so that
# number doesn't need to be re-cleared to make this switch.


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
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database operation failed fetching momentum metrics for {symbol}: {e}") from e

    def _score_momentum(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score momentum metrics on 0-100 scale. Returns marker dict if no real data.

        STALE SUMMARY FIXED (2026-09-17, AQR MOMENTUM PIVOT - see module docstring) - this
        paragraph used to describe a risk-adjusted momentum_6m (50%) + risk-adjusted 12-1 (50%)
        blend matching MSCI's Momentum Index methodology. That is no longer what the code below
        does. Current live scoring: RAW (not risk-adjusted) 12-1 skip-month momentum, weight
        1.0 - the only scored input, matching AQR's actual published momentum factor (Asness,
        Moskowitz & Pedersen 2013, "Value and Momentum Everywhere"). momentum_6m/momentum_3m/
        RSI(14)/MACD-sign/SMA-50/200 positioning are fetched/persisted/displayed but NOT scored
        (informational-only) - none of them are part of AQR's or Carhart's UMD momentum
        construction. Raw momentum_6m/momentum_12m REPLACED 2026-08-25 by a derived 12-1
        construction - see RESOLVED note below.

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
        # AQR MOMENTUM PIVOT (see module docstring): momentum_6m's risk-adjusted leg is gone -
        # AQR's factor (Asness/Moskowitz/Pedersen 2013) is a single raw 12-1 return, not a
        # 6m+12-1 blend. momentum_3m/RSI/MACD/SMA-position remain fetched/persisted/displayed
        # (informational, not scored - same convention already used elsewhere in this codebase
        # for demoted fields).
        weighted_sum = 0.0
        total_weight = 0.0

        # 12-1 momentum (skip most-recent-month, Jegadeesh 1990 / AMP 2013 standard
        # construction) - the ONLY scored input now (weight 1.0). Derived rather than requiring
        # a new stored field: cumulative return from 12mo-ago to 1mo-ago is algebraically
        # (1+momentum_12m/100)/(1+momentum_1m/100) - 1, converted back to a percentage number to
        # match _pct_to_score's expected input convention. RAW, not risk-adjusted (see module
        # docstring's AQR MOMENTUM PIVOT note). Guarded against a near-zero denominator (would
        # require momentum_1m ~ -100%, a stock price going to ~zero in a month - not realistic
        # for a scoreable position, but NaN/Infinity guarded both directions per this codebase's
        # standard convention regardless).
        mom_12m_raw = metrics.get("momentum_12m")
        mom_1m_raw = metrics.get("momentum_1m")
        if mom_12m_raw is not None and mom_1m_raw is not None:
            denom = 1.0 + mom_1m_raw / 100.0
            if abs(denom) > 1e-6:
                mom_12_1 = ((1.0 + mom_12m_raw / 100.0) / denom - 1.0) * 100.0
                if math.isfinite(mom_12_1):
                    mom_12_1_score = self._pct_to_score(mom_12_1)
                    if (
                        mom_12_1_score is not None
                    ):  # _pct_to_score no longer returns None (dead-zone removed 2026-09-16) - guard kept, harmless
                        weighted_sum += mom_12_1_score * 1.0
                        total_weight += 1.0

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

    @staticmethod
    def _pct_to_score(pct_return: float) -> float | None:
        """Convert percentage return to 0-100 score. PASS-1 PROVISIONAL ONLY - always
        overwritten by `update_momentum_sector_relative_mom_12_1`'s universe-wide z-score pass,
        same "Pass-1 curve is scaffolding" relationship every other pillar's absolute curve has
        to its own batch pass (see e.g. growth_scoring.py's `_score_single_growth`).

        -20% = 0, +20% = 100, linear in between.

        pct_return is a percentage NUMBER (e.g. 20.0 for +20%), not a fraction - matches
        load_risk_metrics_daily.py's ret_pct = (price_new - price_old) / price_old * 100,
        which is what momentum_1m/3m/6m/12m are computed as and stored as.

        WEAK-MOMENTUM "DEAD ZONE" REMOVED 2026-09-16 (factor-purity sweep, user: "we do what
        the industry does only"). This used to return None for -3% <= pct_return <= 3%
        ("insufficient conviction") - an invented exclusion zone with no counterpart in any
        published momentum construction (Jegadeesh-Titman, Carhart UMD, AQR, MSCI, S&P all
        z-score/rank the FULL continuous distribution of returns, including near-zero ones;
        "near-zero momentum" is itself real information - a stock going nowhere - not a
        conviction threshold to gate on). Held to the same "must trace to a real published
        methodology, not an invented threshold" bar this session already applied everywhere
        else - it doesn't clear it, so it's gone. `update_momentum_sector_relative_mom_12_1`'s
        own batch pass (the real, live-scoring transform) already had no equivalent dead zone -
        this fixes only the Pass-1 scaffolding curve to match.

        REPLACED WITH A FLAT NEUTRAL PLACEHOLDER 2026-09-17 (factor-purity follow-up, "get rid
        of it" not just verify it's inert - same treatment already applied to Value/Quality/
        Growth's own Pass-1 curves, see value_metrics.py's NEUTRAL_PLACEHOLDER_SCORE for the
        shared rationale). The linear -20%/+20%->0/100 mapping removed here was itself hand-set
        (no cited source for that specific slope/range). Live-audited before removing: this
        exact Pass-1 formula (risk-adjusted momentum_6m + mom_12_1, 50/50, run through this
        function) reconstructed for all 3,241 real symbols with a scored momentum_score and
        diffed against the actual stored value (the real universe-wide z-score computed by
        update_momentum_sector_relative_mom_12_1() below) - 53/3,241 landed within 0.5 points,
        coincidental correlation (confirmed via `_withhold_momentum_below_floor()` returning 0
        symbols currently stuck on Pass-1's value), not survival. `pct_return` is accepted
        (unused) only so call sites don't need updating.
        """
        del pct_return
        return 50.0

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
        mom_12_1_pct: dict[str, float],
    ) -> float | None:
        """Recompute a single symbol's full momentum_score for
        update_momentum_sector_relative_mom_12_1() - split out purely to keep that method's
        cyclomatic complexity within this repo's ruff C901 bound. AQR MOMENTUM PIVOT (see module
        docstring): mom_12_1 alone, weight 1.0 (from the pre-computed universe-wide pct map) -
        momentum_6m/momentum_3m/tech_trend/sma_avg are no longer scored at all.
        """
        if symbol in mom_12_1_pct:
            return round(mom_12_1_pct[symbol], 2)
        logger.debug(
            f"[STOCK_SCORES] {symbol} momentum_score withheld in universe-wide pass: "
            f"mom_12_1 not computable (below MOMENTUM_MIN_WEIGHT={MOMENTUM_MIN_WEIGHT})."
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
        # GROWTH REMOVED FROM COMPOSITE 2026-09-17 (factor-purity pivot: MSCI -> AQR only - see
        # pillar_weights.py's BASE_PILLAR_WEIGHTS docstring for the full citation/rationale).
        # AQR's real factor set has no standalone Growth factor; `growth_score` param is kept
        # (still fetched by the caller for its own unrelated bookkeeping) but no longer feeds
        # composite_score or data_completeness.
        del growth_score
        weights = BASE_PILLAR_WEIGHTS
        composite_val = 0.0
        for pillar_name, pillar_score in (
            ("quality", quality_score),
            ("value", value_score),
            ("risk", risk_score),
            ("momentum", momentum_score_new),
        ):
            if pillar_score is not None:
                composite_val += float(pillar_score) * weights[pillar_name]
        composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)

        all_scores_new: dict[str, float | None] = {
            "quality": float(quality_score) if quality_score is not None else None,
            "value": float(value_score) if value_score is not None else None,
            "risk": float(risk_score) if risk_score is not None else None,
            "momentum": momentum_score_new,
        }
        available_weight = sum(
            BASE_PILLAR_WEIGHTS[pillar] for pillar, score in all_scores_new.items() if score is not None
        )
        data_completeness_new = min(99.99, round(available_weight * 100, 2))
        return composite_score_new, data_completeness_new

    def _withhold_momentum_below_floor(
        self,
    ) -> list[tuple[str, float | None, float, str | None, float, bool]]:
        """Companion to update_momentum_sector_relative_mom_12_1(): finds the COMPLEMENT of
        that method's own correction population - symbols with a real momentum_score and real
        (non-data_unavailable) momentum_metrics, but ineligible for correction (below the
        liquidity floor, or excluded by NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE) - and
        withholds momentum_score (NULL) plus recomputes composite_score/data_completeness/
        data_unavailable to match, rather than leaving Pass 1's stale, potentially-saturated
        curve value in place indefinitely. See update_momentum_sector_relative_mom_12_1()'s own
        "WITHHELD, NOT LEFT STALE" docstring note for the full rationale - this is the scoring-
        pipeline-side fix for exactly the leak a reverted display-layer filter attempt found.

        Returns tuples in the same (symbol, momentum_score, composite_score, components,
        data_completeness, data_unavailable) shape update_momentum_sector_relative_mom_12_1()'s
        own `updates` list uses, so the caller can extend one batch UPDATE with both.
        """
        with _owner().DatabaseContext("write") as cur:
            cur.execute(
                """
                SELECT ss.symbol, ss.composite_score, ss.quality_score, ss.growth_score,
                       ss.value_score, ss.risk_score, ss.components,
                       ss.data_completeness, ss.data_unavailable
                FROM stock_scores ss
                JOIN momentum_metrics mm ON mm.symbol = ss.symbol
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
                WHERE ss.momentum_score IS NOT NULL
                  AND COALESCE(mm.data_unavailable, false) = false
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
        withheld: list[tuple[str, float | None, float, str | None, float, bool]] = []
        for (
            symbol,
            _composite_score_old,
            quality_score,
            growth_score,
            value_score,
            risk_score,
            components_old,
            _dc_old,
            _du_old,
        ) in rows:
            composite_score_new, data_completeness_new = self._recompute_composite_for_row(
                quality_score, growth_score, value_score, risk_score, None
            )
            data_unavailable_new = data_completeness_new < min_completeness_threshold
            components_json = self._components_with_corrected_momentum(components_old, None)
            withheld.append(
                (
                    symbol,
                    None,
                    composite_score_new,
                    components_json,
                    data_completeness_new,
                    data_unavailable_new,
                )
            )
        logger.info(
            f"[STOCK_SCORES] Momentum: withheld momentum_score for {len(withheld)} symbols below the "
            f"liquidity floor / excluded from the scoring population (never reached by the correction "
            f"pass above) - see _withhold_momentum_below_floor's docstring."
        )
        return withheld

    def update_momentum_sector_relative_mom_12_1(self) -> None:
        """Batch pass: replace mom_12_1's Pass-1 PROVISIONAL flat-placeholder score with a
        universe-wide z-score against the current run's universe, then FULLY RECOMPUTE
        momentum_score/composite_score from scratch - mirrors
        `update_growth_sector_neutral_scores()`'s pure-overwrite pattern (loaders/stock_scores/
        growth_scoring.py) exactly, which itself mirrors Quality's, minus the sector grouping.

        NAME IS STALE, KEPT FOR CALL-SITE STABILITY - mom_12_1 is, and remains, UNIVERSE-WIDE
        (`universe_wide_zscore`, not `sector_neutral_zscore` - see this repo's own live-MTUM-
        holdings reversal history in git for why sector-relative was tried and rejected for this
        pillar). Do not reintroduce `sector_neutral_zscore` here without clearing that same bar.

        AQR MOMENTUM PIVOT (2026-09-17, see module docstring's own AQR MOMENTUM PIVOT note):
        mom_6m and the risk-adjustment/risk-free-netting machinery that used to sit here are
        gone - AQR's momentum factor (Asness, Moskowitz & Pedersen 2013, "Value and Momentum
        Everywhere") is a single RAW 12-1 skip-month return, not a risk-adjusted 6m+12-1 blend.
        momentum_3m/tech_trend/sma_avg remain unscored, same as before.

        MECHANISM: compute each symbol's raw mom_12_1 return, then `universe_wide_zscore`/
        `zscore_to_percentile_scale` (loaders/helpers/factor_normalization.py) in place of
        `_pct_to_score`'s flat placeholder - weight 1.0, the only scored input.

        INVESTABILITY FLOOR: liquidity-based (algo_config.min_stock_price/min_adv_dollars,
        same as every other sector-neutral pass - REPLACED the market-cap floor 2026-09-15,
        see LIQUIDITY_FLOOR_JOIN_SQL's own docstring in pillar_weights.py for why) -
        sub-floor illiquid names distort the peer-group percentile boundaries real, investable
        companies get ranked against; those symbols simply aren't included in the CORRECTION
        population above.

        WITHHELD, NOT LEFT STALE (added 2026-09-15, same session - user directive: filtering
        belongs in the scoring pipeline, never bolted onto the display/API layer). A symbol
        below the liquidity floor (or excluded by NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE)
        never reaches the correction pass above, so it would otherwise keep Pass-1's raw,
        un-corrected `_pct_to_score` curve value forever - including that curve's hard
        +-20%-return-to-[0,100] saturation, live-confirmed pegging WHG (Westwood Holdings,
        ~$213K 20-day ADV, below the $500K floor) at momentum_score=100.00. A first attempt
        fixed this by adding a liquidity check to the leaderboard's OWN display filter
        (algo/signals/investable_universe.py) - reverted: that duplicates this pass's own
        eligibility decision in a second place that can drift from it, and only hides the bad
        score instead of fixing it. The real fix is here: `_withhold_momentum_below_floor`
        below finds exactly this complement population (momentum_score IS NOT NULL, momentum
        data itself is fine, but ineligible for correction) and withholds momentum_score
        (NULL, matching MOMENTUM_MIN_WEIGHT's own "insufficient signal, don't fabricate a
        score" convention) rather than leaving Pass 1's stale value in place - so any consumer
        reading `stock_scores` directly (not just the leaderboard) sees a correct, honest
        absence of signal instead of a display-layer-only correction.

        Composite_score recomputed exactly as update_growth_sector_neutral_scores recomputes
        it - from quality_score/value_score/risk_score/growth_score as they currently stand
        (untouched by this pass) plus the new momentum_score, via fixed `BASE_PILLAR_WEIGHTS`.
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
                           mm.momentum_1m, mm.momentum_12m
                    FROM stock_scores ss
                    JOIN momentum_metrics mm ON mm.symbol = ss.symbol
                    JOIN stock_symbols su ON su.symbol = ss.symbol
                    LEFT JOIN company_info_sec cis ON cis.symbol = ss.symbol
                    """
                    + LIQUIDITY_FLOOR_JOIN_SQL
                    + """
                    WHERE ss.momentum_score IS NOT NULL
                      AND COALESCE(mm.data_unavailable, false) = false
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
                    "[STOCK_SCORES] update_momentum_sector_relative_mom_12_1: no eligible rows found - skipping."
                )
                return

            # Raw mom_12_1 (skip-month construction, AQR MOMENTUM PIVOT - see module docstring):
            # no risk-adjustment, no risk-free-rate netting, no mom_6m blend.
            mom_12_1_raw: dict[str, float] = {}
            for row in rows:
                symbol, m1_raw, m12_raw = row[0], row[10], row[11]
                if m1_raw is not None and m12_raw is not None:
                    m1f, m12f = float(m1_raw), float(m12_raw)
                    denom = 1.0 + m1f / 100.0
                    if abs(denom) > 1e-6:
                        mom_12_1 = ((1.0 + m12f / 100.0) / denom - 1.0) * 100.0
                        if math.isfinite(mom_12_1):
                            mom_12_1_raw[symbol] = mom_12_1

            # UNIVERSE-WIDE, not sector-relative - see this module's own
            # update_momentum_sector_relative_mom_12_1 docstring and universe_wide_zscore's
            # docstring in factor_normalization.py for the full evidence trail.
            mom_12_1_pct = zscore_to_percentile_scale(universe_wide_zscore(mom_12_1_raw))
            logger.info(
                f"[STOCK_SCORES] Momentum universe-wide mom_12_1 z-score ({len(mom_12_1_pct)}/{len(rows)} scored)"
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
                    _m12_raw,
                ) = row

                momentum_score_new = self._recompute_momentum_score_for_row(
                    symbol,
                    mom_12_1_pct,
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

            updates.extend(self._withhold_momentum_below_floor())

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
                    SET momentum_score = v.momentum_score::numeric,
                        composite_score = v.composite_score::numeric,
                        components = v.components::jsonb,
                        data_completeness = v.data_completeness::numeric,
                        data_unavailable = v.data_unavailable::boolean,
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
