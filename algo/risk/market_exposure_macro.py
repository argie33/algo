#!/usr/bin/env python3

"""Macro-watch / slow-veto factor mixin for MarketExposure (algo/risk/market_exposure.py).

Split out of market_exposure.py's monolithic MarketExposure class as part of the
2026-09-05 bloater-decomposition pass (same mixin pattern established by
algo/monitoring/position_monitor.py's split, commit 1d8a64f73). Mechanical split only -
no behavior change; every method body here is byte-identical to what was previously
directly on MarketExposure.

Holds the slow-macro / "Layer 3" factor calculations that feed only the slow macro veto
and dashboard/audit display (see market_exposure.py's module docstring, "SLOW MACRO
VETO"): a shared single-series z-score helper, the yield-curve reading + its persistence
check, inflation-expectations reading, the Sahm Rule reading + its ramp scorer, and the
veto itself that combines all three. None of these reference DatabaseContext/AlgoConfig
or anything else patched at the market_exposure module level, so no qualified-attribute-
access trick is needed here (unlike market_exposure_cache.py).
"""

from __future__ import annotations

import math
from datetime import date as _date
from typing import Any

from psycopg2.extensions import cursor as PsycopgCursor


class MarketExposureMacroMixin:
    """Macro-watch / slow-veto factors: yield curve, inflation expectations, Sahm Rule.

    Not usable standalone - relies on the `calculator` instance attribute and the
    YIELD_CURVE_INVERSION_WINDOW_DAYS/INFLATION_EXPECTATIONS_TAIL_Z/SLOW_MACRO_VETO_CAP
    class constants, all defined on MarketExposure itself (same declare-for-mypy pattern
    as algo/monitoring/position_health_checks.py's `config: Any`).
    """

    calculator: Any
    YIELD_CURVE_INVERSION_WINDOW_DAYS: int
    INFLATION_EXPECTATIONS_TAIL_Z: float
    SLOW_MACRO_VETO_CAP: float

    def _single_series_zscore_factor(
        self,
        eval_date: _date,
        cur: PsycopgCursor[Any],
        series_id: str,
        higher_is_worse: bool,
        lookback: int = 10000,
    ) -> dict[str, Any]:
        """Shared helper: z-score a single economic_data series against its own real
        history (standard Barra/Axioma-style normalization - see MarketFactorCalculator
        ._sample_zscore). Degrades to data_unavailable rather than raising - these are
        macro-watch-only inputs now (see module docstring), not scored composite factors.
        """
        cur.execute(
            "SELECT value::float FROM economic_data WHERE series_id = %s AND date <= %s "
            "AND value IS NOT NULL ORDER BY date DESC LIMIT %s",
            (series_id, eval_date, lookback),
        )
        rows = [r[0] for r in cur.fetchall()]
        if not rows:
            return {"data_unavailable": True, "reason": f"No {series_id} data on or before {eval_date}"}
        current = rows[0]
        if math.isnan(current) or math.isinf(current):
            return {"data_unavailable": True, "reason": f"Non-finite {series_id} reading"}
        z = self.calculator._sample_zscore(current, rows)
        if z is None:
            return {
                "data_unavailable": True,
                "reason": (
                    f"Cannot z-score {series_id}: insufficient history (have {len(rows)}, need 15+) "
                    f"or zero variance in that history"
                ),
                "value": round(current, 3),
            }
        stress_z = z if higher_is_worse else -z
        return {
            "score": self.calculator._zscore_to_score(stress_z),
            "value": round(current, 3),
            "z": round(stress_z, 2),
        }

    def _yield_curve_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Yield curve reading: T10Y2Y + T10Y3M, each z-scored against own history,
        averaged - MACRO WATCH ONLY (see module docstring): not scored in the composite,
        feeds only the slow macro veto's persistence check (_yield_curve_inverted_persistent)
        and this dict's own z-scored snapshot for dashboard/audit display.

        T10Y2Y and T10Y3M are 0.941 correlated over their real 26-year FRED history (both
        backfilled to 1990 - see scripts/backfill_economic_data_history.py), i.e.
        substantially the same underlying curve-slope information. Both are still read
        (averaged into one z-score here) rather than picking just one, preserving the small,
        real divergence between the short and long end at regime turns (2001, 2019) - they
        already share one combined read, not two separately-weighted votes, so this isn't
        the double-counting pattern the pre-redesign file used to find and fix elsewhere. A
        more negative (more inverted) spread is the bearish direction for both, so z is
        flipped before scoring.
        """
        pieces = []
        detail: dict[str, Any] = {}
        for series_id, key in (("T10Y2Y", "t10y2y"), ("T10Y3M", "t10y3m")):
            r = self._single_series_zscore_factor(eval_date, cur, series_id, higher_is_worse=False)
            detail[key] = r
            if not r.get("data_unavailable"):
                pieces.append(r["score"])
        if not pieces:
            return {"data_unavailable": True, "reason": "Neither T10Y2Y nor T10Y3M could be z-scored", **detail}
        return {"score": round(sum(pieces) / len(pieces), 1), **detail}

    def _yield_curve_inverted_persistent(self, eval_date: _date, cur: PsycopgCursor[Any]) -> bool:
        """True if the averaged T10Y2Y/T10Y3M spread has been negative (inverted) on
        EVERY available trading day for the trailing YIELD_CURVE_INVERSION_WINDOW_DAYS
        sessions (~3 months) - a persistence check for the slow macro veto, distinct
        from _yield_curve_factor's single-day z-score read. Requires a full window of
        real data (returns False, not data_unavailable, if there isn't one - this is a
        veto input, and an unproven/incomplete signal must not trip a cap).
        """
        cur.execute(
            """
            SELECT a.date, (a.value + b.value) / 2.0
            FROM economic_data a
            JOIN economic_data b ON a.date = b.date AND b.series_id = 'T10Y3M'
            WHERE a.series_id = 'T10Y2Y' AND a.date <= %s
              AND a.value IS NOT NULL AND b.value IS NOT NULL
            ORDER BY a.date DESC LIMIT %s
            """,
            (eval_date, self.YIELD_CURVE_INVERSION_WINDOW_DAYS),
        )
        rows = cur.fetchall()
        if len(rows) < self.YIELD_CURVE_INVERSION_WINDOW_DAYS:
            return False
        return all(float(r[1]) < 0 for r in rows)

    def _inflation_expectations_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Inflation Expectations reading: T5YIE + T10YIE breakeven average, z-scored -
        MACRO WATCH ONLY (see module docstring): not scored in the composite, feeds only
        the slow macro veto's tail-extreme check and this dict's own snapshot for
        dashboard/audit display.

        Averaging the 5Y and 10Y tenors of the same market-implied measurement (TIPS vs.
        nominal Treasury spread) is a standard fixed-income simplification - confirmed
        0.84 correlation between the two tenors, i.e. genuinely the same underlying
        signal read at two maturities. Elevated breakeven inflation implies the Fed is
        more likely to stay restrictive - the bearish direction for risk assets, so
        higher_is_worse.
        """
        cur.execute(
            """
            SELECT a.date, (a.value + b.value) / 2.0
            FROM economic_data a
            JOIN economic_data b ON a.date = b.date AND b.series_id = 'T10YIE'
            WHERE a.series_id = 'T5YIE' AND a.date <= %s
              AND a.value IS NOT NULL AND b.value IS NOT NULL
            ORDER BY a.date DESC LIMIT 10000
            """,
            (eval_date,),
        )
        rows = [float(r[1]) for r in cur.fetchall()]
        if not rows:
            return {"data_unavailable": True, "reason": f"No overlapping T5YIE/T10YIE data on or before {eval_date}"}
        current = rows[0]
        if math.isnan(current) or math.isinf(current):
            return {"data_unavailable": True, "reason": "Non-finite breakeven average"}
        z = self.calculator._sample_zscore(current, rows)
        if z is None:
            return {
                "data_unavailable": True,
                "reason": f"Insufficient breakeven history to z-score (have {len(rows)}, need 15+)",
                "value": round(current, 3),
            }
        return {"score": self.calculator._zscore_to_score(z), "value": round(current, 3), "z": round(z, 2)}

    @staticmethod
    def _sahm_ramp_score(sahm_value: float) -> float:
        """Map a Sahm value to a 0-100 factor score via a ramp anchored on Sahm's own real,
        published 0.50pp trigger - not a generic z-score.

        The raw historical Sahm-value series is heavily right-skewed (mean 0.497, stdev
        1.265, driven almost entirely by a handful of extreme 2008-09/2020 crisis
        readings) even though 80% of months never came remotely close to triggering. A
        generic sample z-score against that distribution would call a reading of 0.0
        "roughly average" purely because a few historic crisis spikes drag the mean up
        near the trigger threshold - the wrong tool for a fundamentally regime-switching
        statistic. This ramp instead respects the threshold's real, research-backed
        meaning directly: 100 at or below 0 (no recessionary signal at all), linearly
        down to 40 exactly AT the literal 0.50pp trigger, continuing down to 0 by +1.5pp.
        """
        if sahm_value <= 0.0:
            return 100.0
        if sahm_value < 0.50:
            return 100.0 - (sahm_value / 0.50) * 60.0
        if sahm_value >= 1.50:
            return 0.0
        return 40.0 - ((sahm_value - 0.50) / 1.0) * 40.0

    def _sahm_rule_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Sahm Rule recession indicator, computed from UNRATE (FRED, monthly) -
        MACRO WATCH ONLY (see module docstring): not scored in the composite, feeds only
        the slow macro veto's "triggered" check and this dict's own snapshot for
        dashboard/audit display.

        Real-time Sahm Rule = (3-month average unemployment rate) minus (the minimum
        3-month average unemployment rate over the trailing 12 months). "triggered"
        (>= 0.50pp) is reported for transparency/logging/dashboard display and directly
        drives the slow macro veto. Requires 15 months of history (3 for the current
        average, 12 more for the trailing-minimum window); degrades to data_unavailable
        rather than raising.
        """
        cur.execute(
            "SELECT value::float, date FROM economic_data "
            "WHERE series_id = 'UNRATE' AND date <= %s AND value IS NOT NULL "
            "ORDER BY date DESC LIMIT 20",
            (eval_date,),
        )
        rows = cur.fetchall()
        if len(rows) < 15:
            return {
                "data_unavailable": True,
                "reason": f"Insufficient UNRATE history for Sahm Rule (have {len(rows)} months, need 15+)",
            }
        values = [float(r[0]) for r in rows]
        if any(math.isnan(v) or math.isinf(v) for v in values):
            return {"data_unavailable": True, "reason": "Non-finite UNRATE reading in trailing window"}

        # rows[0] is the most recent month; 3-month trailing averages ending at each month
        # index i (i=0 is "ending this month") for i in 0..12, matching the official
        # methodology's 12-month lookback window of 3-month averages.
        trailing_3mo_avgs = [sum(values[i : i + 3]) / 3.0 for i in range(13)]
        current_avg = trailing_3mo_avgs[0]
        trailing_12mo_min = min(trailing_3mo_avgs[1:13])
        sahm_value = current_avg - trailing_12mo_min
        return {
            "score": self._sahm_ramp_score(sahm_value),
            "value": round(sahm_value, 2),
            "triggered": sahm_value >= 0.50,
        }

    def _slow_macro_veto(
        self, eval_date: _date, cur: PsycopgCursor[Any], sahm: dict[str, Any], infl: dict[str, Any]
    ) -> dict[str, Any]:
        """Layer 3, new: a deliberately slow, wide, rare tail-risk veto fed by Sahm Rule,
        yield-curve inversion persistence, and inflation-expectations tail extremes.

        Estrella & Mishkin (1998): yield-curve inversion leads recessions by 6-24
        months. Real recession/stress signals, but the wrong horizon for this system's
        days-to-weeks swing-trading exposure dial - so they no longer earn composite
        weight (see module docstring). Demoted here instead of dropped, because the
        underlying signals ARE real; a single trip caps exposure to SLOW_MACRO_VETO_CAP
        (45%) - a background elevated-risk flag, less severe than the daily-signal
        vetoes above, reflecting the genuinely longer horizon these operate on. Multiple
        simultaneous triggers still cap to the same 45% (not stacked lower) since all
        three are correlated reads of the same underlying macro-stress regime, not
        independent risks that compound.
        """
        reasons: list[str] = []

        if not sahm.get("data_unavailable") and sahm.get("triggered"):
            reasons.append(f"Sahm Rule triggered ({sahm.get('value')}pp >= 0.50pp recession signal)")

        if self._yield_curve_inverted_persistent(eval_date, cur):
            reasons.append(
                f"Yield curve (T10Y2Y/T10Y3M avg) inverted continuously for "
                f"{self.YIELD_CURVE_INVERSION_WINDOW_DAYS}+ trading days"
            )

        if not infl.get("data_unavailable"):
            infl_z = infl.get("z")
            if infl_z is not None and infl_z >= self.INFLATION_EXPECTATIONS_TAIL_Z:
                reasons.append(f"Inflation expectations at tail extreme (z={infl_z})")

        if reasons:
            return {"triggered": True, "reasons": reasons, "cap": self.SLOW_MACRO_VETO_CAP}
        return {"triggered": False, "reasons": [], "cap": 100.0}
