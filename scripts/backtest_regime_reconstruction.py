#!/usr/bin/env python3
"""
STANDALONE, READ-ONLY historical market-regime reconstruction (one-off analysis tool).

NOT a production loader - never scheduled, never called by orchestrator/loaders. Does not
write to market_health_daily, market_exposure_daily, credit_spreads, economic_data, or any
other production table. Reads price_daily/price_weekly/economic_data (already-loaded
history) and writes its own output to a local CSV only.

Built 2026-09-04 (real-money-readiness goal session) to answer: are `market_exposure_daily`'s
36 observed days (zero correction/caution) really the full picture, or just how far back the
live production snapshot table happens to reach? Answer: the latter. The underlying raw data
(price_daily's SPY/^VIX going back to 1993/1992, economic_data's FRED series going back to
1990-2003 for most series) is far deeper than market_exposure_daily's ~14-month/36-day
production window, which is a daily-incremental-snapshot loader artifact, not a real data
ceiling. This script replicates algo/risk/market_exposure.py's exact scoring/veto logic
against that deeper raw history to reconstruct what regime labels WOULD have been.

FAITHFULNESS TO PRODUCTION LOGIC - what's replicated exactly vs. approximated:
  - trend_30wk: EXACT replica of market_factor_calculator.py's trend_30wk() - SPY close vs
    30-week SMA from price_weekly, same >/<= comparison.
  - vix_regime: uses price_daily's ^VIX close as the level (production reads this same value
    via market_health_daily.vix_level, sourced from price_daily per
    loaders/market_health_fetchers.py's VIXFetcher docstring - "single source of truth").
    Rising = vs 5 trading days ago, same as production. Same level tiers (<15/15-25/25-35/35+)
    and same _vix_score formula (10pt flat rising penalty).
  - selling_pressure: EXACT replica - 25-session window, heavy-volume down days (close<prev,
    volume>trailing-50d-avg), same 0-2/3-4/5+ score bands.
  - _has_market_confirmation (veto 4): EXACT replica - 30-day window, close >= prior*1.017
    on rising volume.
  - credit_spread (HY OAS, BAMLH0A0HYM2): uses economic_data's already-loaded history, which
    only starts 2023-08-22 - NOT a backfill gap this script can fix. market_exposure.py's own
    _credit_spread() docstring documents that FRED changed its ICE BofA index distribution
    policy in April 2026 to serve only a rolling ~3-year window regardless of requested
    range - a permanent external ceiling, not fixable via a wider fetch_from_fred() call.
    Before 2023-08-22, veto 5 is marked "not evaluated" (not "passed") - see CREDIT SPREAD
    GAP note in the final report.
  - slow_macro_veto (Sahm/yield-curve/inflation-expectations): EXACT replica using
    economic_data's UNRATE (from 2000), T10Y2Y/T10Y3M (from 1990), T5YIE/T10YIE (from 2003) -
    all already loaded deep enough to cover this reconstruction's full window.
  - breadth (veto 1's b50 < 30% leg) and the vol-managed multiplier: DELIBERATELY OMITTED.
    See "WHY BREADTH IS SKIPPED" below - it does not change the regime label given how the
    composite score's arithmetic actually works out.
  - Pillar 3 (breadth&sentiment/participation/ad_line/new_highs_lows/aaii/put_call_ratio):
    OMITTED - carries ZERO composite weight in production (W_PILLAR_CONFIRM=0.0) and does
    not feed any veto, so it cannot affect the regime label or exposure_pct at all.

WHY BREADTH IS SKIPPED (worked out from the real production formula, not a shortcut taken
blind): composite score = trend_pts (100% of the score, since W_PILLAR_RISK=W_PILLAR_CONFIRM
=0.0) = 100.0 if SPY>30wkMA else 0.0, times vol_mult. Veto 1 (SPY<30wkMA AND breadth<30%) only
evaluates when SPY is ALREADY below its 30-week MA - i.e. only when scaled_score is ALREADY
0 (trend bearish => score=0 => scaled_score=0*vol_mult=0). final=min(scaled_score, cap) can
only make a 0 stay 0 or go lower - it can never raise it. So veto 1 (and every other veto,
when trend is bearish) is mathematically inert for the regime LABEL: whenever SPY is below its
30-week MA, final exposure is 0% and regime is "correction" regardless of what any veto's cap
says. Vetoes only matter for the regime label during BULLISH trend weeks (where they can pull
a would-be 100% down into caution/uptrend_under_pressure territory) - and veto 1 specifically
never fires in that branch (it's gated on the trend being bearish). This was verified against
the real compute()/tier_for_exposure() control flow, not assumed.

METHOD: weekly cadence (matches trend_30wk's own weekly granularity - the score itself only
changes on weekly SPY closes). For each week-ending trading date with a full 30-week SPY
history: compute trend_30wk (bullish/bearish). If bullish, additionally evaluate vetoes
2/3/4/5/6 (VIX>40 rising, selling-pressure days, no market confirmation, HY OAS>8.5%, slow
macro) to find the capped exposure_pct and bucket it via the real EXPOSURE_TIERS thresholds
(70/45/25/0, from algo/risk/exposure_policy.py). If bearish, regime is unconditionally
"correction" (exposure_pct=0) per the reasoning above - vetoes still computed and recorded
for the halt_reasons audit trail, but they cannot change the label.

vol-managed multiplier: production pins this to inert 1.0 for eval_date < 2026-08-24 (see
market_exposure.py's _vol_managed_multiplier docstring - "not live in production before that
date... must reproduce what was actually decided then, not silently apply today's code to
history"). This reconstruction's window is 1993-2026, i.e. almost entirely before that
activation date, so vol_mult=1.0 throughout except the final ~2 weeks - implemented exactly
(same formula, same [0.25,2.0] cap) for full fidelity in that tail, inert everywhere else.

Output: scripts/output/regime_reconstruction_history.csv (local file only).
"""

from __future__ import annotations

import csv
import itertools
import math
import os
import sys
from datetime import date as _date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")

CONN = psycopg2.connect(
    host=os.environ["DB_HOST"],
    dbname=os.environ["DB_NAME"],
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ["DB_PASSWORD"],
    port=os.environ.get("DB_PORT", 5432),
)
CONN.set_session(readonly=True)

VOL_MANAGED_ACTIVATION_DATE = _date(2026, 8, 24)
CREDIT_SPREAD_DATA_START = _date(2023, 8, 22)  # real economic_data floor, see docstring above


def annualized_std(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    v = math.sqrt(var)
    if math.isnan(v) or math.isinf(v):
        return None
    return v * math.sqrt(252)


def main() -> None:  # noqa: C901
    cur = CONN.cursor()

    # ---- 1. Weekly SPY closes + 30-week SMA (EXACT replica of trend_30wk) ----
    cur.execute(
        """
        SELECT date, close,
               AVG(close) OVER (ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS sma30
        FROM price_weekly
        WHERE symbol = 'SPY' AND close IS NOT NULL
        ORDER BY date
        """
    )
    weekly_rows = cur.fetchall()
    weeks: list[tuple[_date, float, float]] = [(d, float(c), float(s)) for d, c, s in weekly_rows if s is not None]
    print(f"Weekly SPY history usable for trend_30wk: {weeks[0][0]} to {weeks[-1][0]} ({len(weeks)} weeks)")

    # ---- 2. Daily VIX (price_daily ^VIX) for level+rising, keyed by date ----
    cur.execute("SELECT date, close FROM price_daily WHERE symbol = '^VIX' AND close IS NOT NULL ORDER BY date")
    vix_daily = {d: float(c) for d, c in cur.fetchall()}
    vix_dates_sorted = sorted(vix_daily.keys())

    # ---- 3. Daily SPY close/volume for selling_pressure + market_confirmation ----
    cur.execute("SELECT date, close, volume FROM price_daily WHERE symbol = 'SPY' AND close IS NOT NULL ORDER BY date")
    spy_daily_rows = cur.fetchall()
    spy_daily = {d: (float(c), float(v) if v is not None else None) for d, c, v in spy_daily_rows}
    spy_dates_sorted = sorted(spy_daily.keys())

    # ---- 4. Credit spread (HY OAS) daily, economic_data (2023-08-22+ only, real ceiling) ----
    cur.execute(
        "SELECT date, value::float FROM economic_data WHERE series_id = 'BAMLH0A0HYM2' "
        "AND value IS NOT NULL ORDER BY date"
    )
    hy_daily = dict(cur.fetchall())
    hy_dates_sorted = sorted(hy_daily.keys())

    # ---- 5. Yield curve daily (T10Y2Y/T10Y3M avg), for persistence check ----
    cur.execute(
        """
        SELECT a.date, (a.value + b.value) / 2.0
        FROM economic_data a
        JOIN economic_data b ON a.date = b.date AND b.series_id = 'T10Y3M'
        WHERE a.series_id = 'T10Y2Y' AND a.value IS NOT NULL AND b.value IS NOT NULL
        ORDER BY a.date
        """
    )
    yc_daily = {d: float(v) for d, v in cur.fetchall()}
    yc_dates_sorted = sorted(yc_daily.keys())

    # ---- 6. Inflation expectations daily (T5YIE/T10YIE avg) ----
    cur.execute(
        """
        SELECT a.date, (a.value + b.value) / 2.0
        FROM economic_data a
        JOIN economic_data b ON a.date = b.date AND b.series_id = 'T10YIE'
        WHERE a.series_id = 'T5YIE' AND a.value IS NOT NULL AND b.value IS NOT NULL
        ORDER BY a.date
        """
    )
    infl_daily = {d: float(v) for d, v in cur.fetchall()}
    infl_dates_sorted = sorted(infl_daily.keys())

    # ---- 7. Monthly UNRATE for Sahm rule ----
    cur.execute(
        "SELECT date, value::float FROM economic_data WHERE series_id = 'UNRATE' AND value IS NOT NULL ORDER BY date"
    )
    unrate_rows = cur.fetchall()
    unrate_dates_sorted = [d for d, _ in unrate_rows]
    unrate_vals = [v for _, v in unrate_rows]

    import bisect

    def sample_zscore(current: float, history: list[float]) -> float | None:
        n = len(history)
        if n < 15:
            return None
        mean = sum(history) / n
        var = sum((x - mean) ** 2 for x in history) / (n - 1)
        sd = math.sqrt(var)
        if sd < 1e-9:
            return None
        z = (current - mean) / sd
        if math.isnan(z) or math.isinf(z):
            return None
        return z

    def zscore_to_score(z: float, cap: float = 2.5) -> float:
        if math.isnan(z) or math.isinf(z):
            return 50.0
        return max(0.0, min(100.0, 50.0 - (z / cap) * 50.0))

    def vix_score(vix: float, rising: bool) -> float:
        if vix < 15:
            level = 100.0
        elif vix < 25:
            level = 80.0
        elif vix < 35:
            level = 40.0
        else:
            level = 0.0
        return max(0.0, level - (10.0 if rising else 0.0))

    def sahm_ramp_score(v: float) -> float:
        if v <= 0.0:
            return 100.0
        if v < 0.50:
            return 100.0 - (v / 0.50) * 60.0
        if v >= 1.50:
            return 0.0
        return 40.0 - ((v - 0.50) / 1.0) * 40.0

    def sahm_for(d: _date) -> dict[str, Any]:
        i = bisect.bisect_right(unrate_dates_sorted, d)
        rows = unrate_vals[max(0, i - 20) : i][::-1]  # most-recent-first, up to 20
        if len(rows) < 15:
            return {"data_unavailable": True}
        trailing = [sum(rows[k : k + 3]) / 3.0 for k in range(13)]
        current_avg = trailing[0]
        trailing_min = min(trailing[1:13])
        val = current_avg - trailing_min
        return {"value": val, "triggered": val >= 0.50}

    def yc_inverted_persistent(d: _date) -> bool:
        i = bisect.bisect_right(yc_dates_sorted, d)
        window_dates = yc_dates_sorted[max(0, i - 63) : i]
        if len(window_dates) < 63:
            return False
        return all(yc_daily[wd] < 0 for wd in window_dates)

    def infl_tail(d: _date) -> bool:
        i = bisect.bisect_right(infl_dates_sorted, d)
        window_dates = infl_dates_sorted[:i]
        if not window_dates:
            return False
        current = infl_daily[window_dates[-1]]
        hist = [infl_daily[wd] for wd in window_dates[-10000:]]
        z = sample_zscore(current, hist)
        return z is not None and z >= 2.0

    def vol_mult_for(d: _date) -> float:
        if d < VOL_MANAGED_ACTIVATION_DATE:
            return 1.0
        i = bisect.bisect_right(spy_dates_sorted, d)
        window_dates = spy_dates_sorted[max(0, i - 3000) : i]
        closes = [spy_daily[wd][0] for wd in window_dates]
        if len(closes) < 252:
            return 1.0
        rets = []
        for prev, curr in itertools.pairwise(closes):
            if prev <= 0 or curr <= 0:
                continue
            r = (curr - prev) / prev
            if not (math.isnan(r) or math.isinf(r)):
                rets.append(r)
        if len(rets) < 252:
            return 1.0
        target = annualized_std(rets)
        realized = annualized_std(rets[-21:])
        if target is None or realized is None or realized <= 0:
            return 1.0
        w = target / realized
        if math.isnan(w) or math.isinf(w):
            return 1.0
        return max(0.25, min(2.0, w))

    def exposure_tier(pct: float) -> str:
        if pct >= 70:
            return "confirmed_uptrend"
        if pct >= 45:
            return "uptrend_under_pressure"
        if pct >= 25:
            return "caution"
        return "correction"

    spy_pos_map = {dt: i for i, dt in enumerate(spy_dates_sorted)}

    results: list[dict[str, Any]] = []
    for week_end, spy_close, sma30 in weeks:
        bullish = spy_close > sma30

        # --- always compute vetoes 2/3/4/5/6 for the audit trail, even on bearish weeks ---
        halt_reasons = []
        cap = 100.0

        # Veto 2: VIX > 40 rising
        vi = bisect.bisect_right(vix_dates_sorted, week_end)
        vix_val = None
        vix_rising = False
        if vi >= 1:
            recent_vix_dates = vix_dates_sorted[max(0, vi - 6) : vi]
            if recent_vix_dates:
                vix_val = vix_daily[recent_vix_dates[-1]]
                if len(recent_vix_dates) >= 6:
                    vix_rising = vix_val > vix_daily[recent_vix_dates[0]]
        if vix_val is not None and vix_val > 40 and vix_rising:
            halt_reasons.append(f"VIX {vix_val:.1f} rising > 40")
            cap = min(cap, 30.0)

        # Veto 3: selling pressure (25-session window, heavy down days vs trailing-50 avg vol)
        si = bisect.bisect_right(spy_dates_sorted, week_end)
        window_dates = spy_dates_sorted[max(0, si - 75) : si]  # need extra history for the 50d avg lookback
        dist_count = None
        if len(window_dates) >= 51:
            last25 = window_dates[-25:]
            dist = 0
            for wd in last25:
                p = spy_pos_map[wd]
                if p < 1:
                    continue
                prev_close = spy_daily[spy_dates_sorted[p - 1]][0]
                close_, vol_ = spy_daily[wd]
                if p < 50:
                    continue
                avg50_window = spy_dates_sorted[p - 49 : p]
                avg50 = sum(spy_daily[x][1] or 0.0 for x in avg50_window) / len(avg50_window)
                if close_ < prev_close and (vol_ or 0.0) > avg50:
                    dist += 1
            dist_count = dist
        if dist_count is not None:
            if dist_count >= 5:
                halt_reasons.append(f"{dist_count} selling-pressure days >= 5")
                cap = min(cap, 35.0)

        # Veto 4: no market confirmation while below 30wk MA (30-day window, >=1.7% up on rising vol)
        has_confirmation = False
        window30 = spy_dates_sorted[max(0, si - 31) : si]
        for k in range(1, len(window30)):
            prev_c, prev_v = spy_daily[window30[k - 1]]
            c, v = spy_daily[window30[k]]
            if prev_c and c >= prev_c * 1.017 and (v or 0) > (prev_v or 0):
                has_confirmation = True
                break
        if not bullish and not has_confirmation:
            halt_reasons.append("No market confirmation signal while SPY below 30-week MA")
            cap = min(cap, 40.0)

        # Veto 5: HY credit spread > 8.5% -- only evaluable from 2023-08-22 onward
        hi = bisect.bisect_right(hy_dates_sorted, week_end)
        hy_val = None
        credit_spread_evaluated = week_end >= CREDIT_SPREAD_DATA_START
        if hi >= 1 and credit_spread_evaluated:
            hy_val = hy_daily[hy_dates_sorted[hi - 1]]
            if hy_val > 8.5:
                halt_reasons.append(f"HY credit spread {hy_val:.2f}% > 8.5%")
                cap = min(cap, 30.0)

        # Veto 6: slow macro (Sahm / yield-curve persistence / inflation tail)
        sahm = sahm_for(week_end)
        slow_reasons = []
        if not sahm.get("data_unavailable") and sahm.get("triggered"):
            slow_reasons.append("sahm")
        if yc_inverted_persistent(week_end):
            slow_reasons.append("yield_curve_persistent")
        if infl_tail(week_end):
            slow_reasons.append("inflation_tail")
        if slow_reasons:
            halt_reasons.append("slow_macro_veto:" + "+".join(slow_reasons))
            cap = min(cap, 45.0)

        vm = vol_mult_for(week_end)
        raw_score = 100.0 if bullish else 0.0
        scaled = max(0.0, min(100.0, raw_score * vm))
        final = min(scaled, cap)
        regime = exposure_tier(final)

        results.append(
            {
                "date": week_end,
                "spy_close": spy_close,
                "sma30": sma30,
                "trend_bullish": bullish,
                "vix": vix_val,
                "vix_rising": vix_rising,
                "selling_pressure_days": dist_count,
                "has_market_confirmation": has_confirmation,
                "hy_oas": hy_val,
                "credit_spread_evaluated": credit_spread_evaluated,
                "vol_mult": round(vm, 3),
                "final_exposure_pct": round(final, 1),
                "regime": regime,
                "halt_reasons": ";".join(halt_reasons),
            }
        )

    out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "regime_reconstruction_history.csv"
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print(f"Wrote {len(results)} weekly rows to {out_path}")

    # ---- Summary ----
    from collections import Counter

    counts = Counter(r["regime"] for r in results)
    print("\nRegime distribution (full history, weekly):")
    for regime_key in ["correction", "caution", "uptrend_under_pressure", "confirmed_uptrend"]:
        print(f"  {regime_key:24s} {counts.get(regime_key, 0):5d} weeks")

    # Post-2023-08-22 subset (credit spread veto fully evaluable)
    post = [r for r in results if r["credit_spread_evaluated"]]
    counts_post = Counter(r["regime"] for r in post)
    print(f"\nRegime distribution (2023-08-22 onward, {len(post)} weeks, credit-spread veto fully live):")
    for regime_key in ["correction", "caution", "uptrend_under_pressure", "confirmed_uptrend"]:
        print(f"  {regime_key:24s} {counts_post.get(regime_key, 0):5d} weeks")

    print("\nSanity-check spot dates:")
    for check_date, label in [
        (_date(2000, 3, 24), "dot-com peak"),
        (_date(2002, 10, 4), "dot-com trough"),
        (_date(2008, 10, 10), "GFC crisis"),
        (_date(2009, 3, 6), "GFC trough"),
        (_date(2020, 3, 20), "COVID crash"),
        (_date(2022, 6, 17), "2022 bear low"),
        (_date(2026, 8, 28), "recent (production window)"),
    ]:
        # find nearest week_end on/before check_date
        candidates = [r for r in results if r["date"] <= check_date]
        if not candidates:
            print(f"  {label} ({check_date}): no data")
            continue
        row = candidates[-1]
        print(
            f"  {label} ({row['date']}): regime={row['regime']}, exposure={row['final_exposure_pct']}%, "
            f"spy_vs_30wk={'above' if row['trend_bullish'] else 'BELOW'}, halts=[{row['halt_reasons']}]"
        )


if __name__ == "__main__":
    main()
