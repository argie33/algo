#!/usr/bin/env python3
"""Regression tests for algo/signals/buy_signal_generator.py::BuySignalGenerator.run()'s
edge-triggering, covering two bugs found and fixed on separate dates:

1. (2026-08-18, bc0047231) This loader emitted a new BUY/SELL row every single day a stock
   remained beyond its swing pivot, instead of once on the bar the breakout/breakdown actually
   happened (Pine's ta.crossover/ta.crossunder mark only the crossing bar). Live audit against
   the DB on 2026-08-17 found 73% of that day's BUY rows and 64% of its SELL rows were re-fires
   of a condition already true the day before, not fresh crossovers.

2. (2026-08-19) The bc0047231 fix compared "is the raw condition true this bar vs. last bar",
   which is NOT what the real Pine script does. Getting the actual Pine source (user-provided)
   revealed it tracks an explicit in-position state machine:
       inPosition := buy[1] ? true : sellSignal[1] ? false : inPosition[1]
       buyStudy = buy and flat          (flat = not inPosition)
       sellStudy = sellSignal and inPosition
   Two concrete divergences from the source: (a) a SELL should never fire without an open
   position behind it (a bare breakdown with no prior BUY plots nothing in Pine); (b) once in a
   position, price dipping back under the pivot and re-breaking out again must NOT re-fire BUY
   before a real SELL closes the position - a same-bar-vs-previous-bar comparison would
   incorrectly re-fire in that case, since it can't tell "still holding a fresh breakout" from
   "genuinely re-broke out after a reversal".

These tests build a synthetic series with a warm-up sawtooth (establishing a real, strategy-1
swing pivot the normal way, not via the no-history fallback), then a clean breakout/breakdown
that holds for 7 more bars without ever reversing, and assert exactly one signal fires during
the hold period - the crossing bar itself, not one per bar spent beyond the pivot.

Note: only a *confirmed* Pine-equivalent pivot (strict pivothigh/pivotlow(3,3), not the relaxed
fallback tiers in BuySignalGenerator._find_swing_high/_find_swing_low) may trigger a signal, so
there is no "day 1 fallback fires a spurious signal" case to work around here as there was
before 2026-08-19 - an unconfirmed early pivot now correctly produces no signal at all, exactly
like Pine's `na`.
"""

from algo.signals.buy_signal_generator import BuySignalGenerator

WARMUP_BARS = 40


def _row(d, o, h, lo, c, sma_50=50.0, sma_200=40.0, rsi=55.0, macd=1.0, macd_signal=0.5):
    return {
        "date": d,
        "open": o,
        "high": h,
        "low": lo,
        "close": c,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "volume": 1_000_000,
        "atr": 1.0,
        "rsi": rsi,
        "macd": macd,
        "macd_signal": macd_signal,
        "ema_21": c,
        "adx": 25.0,
        "mansfield_rs": 0.0,
    }


def _date(i):
    # Simple sequential fake dates, never parsed as real calendar dates by the generator.
    return f"2026-01-{i + 1:02d}" if i < 30 else f"2026-02-{i - 29:02d}"


def _build_breakout_and_hold_rows():
    """40-bar sawtooth warm-up (real, repeatedly-confirmed swing high pinned at 58.5) so the
    pivot in effect at the bar of interest comes from strategy 1, not the no-history fallback.
    Bar 40 breaks out to 62.0 and price keeps climbing for 7 more bars without ever dropping
    back under the pivot - the "still active, not a new event" scenario.
    """
    rows = []
    for i in range(WARMUP_BARS):
        h = 58.5 if i % 5 == 2 else 58.0
        rows.append(_row(_date(i), 58.0, h, 57.5, 57.8))
    rows.append(_row(_date(WARMUP_BARS), 61.0, 62.0, 60.5, 61.5))
    for i in range(WARMUP_BARS + 1, WARMUP_BARS + 8):
        rows.append(_row(_date(i), 61.0, 62.0 + i * 0.05, 60.5, 61.8))
    return rows


def _build_breakdown_and_hold_rows():
    """Sawtooth warm-up pins a real swing low at 59.5, and NO swing high ever confirms (highs
    are held flat at 60.5), so a symbol never enters a position via BUY. Bar 40 breaks down to
    56.0 and price keeps falling for 7 more bars without reclaiming the pivot - a bare
    breakdown with no prior BUY behind it.
    """
    rows = []
    for i in range(WARMUP_BARS):
        low = 59.5 if i % 5 == 2 else 60.0
        rows.append(
            _row(_date(i), 60.0, 60.5, low, 60.2, sma_50=50.0, sma_200=55.0, rsi=45.0, macd=-1.0, macd_signal=-0.5)
        )
    rows.append(
        _row(
            _date(WARMUP_BARS), 57.0, 57.5, 56.0, 56.5, sma_50=50.0, sma_200=55.0, rsi=45.0, macd=-1.0, macd_signal=-0.5
        )
    )
    for i in range(WARMUP_BARS + 1, WARMUP_BARS + 8):
        rows.append(
            _row(
                _date(i),
                56.0,
                56.5,
                55.5 - i * 0.05,
                56.0,
                sma_50=50.0,
                sma_200=55.0,
                rsi=45.0,
                macd=-1.0,
                macd_signal=-0.5,
            )
        )
    return rows


def _build_buy_then_breakdown_rows():
    """40-bar warm-up confirms BOTH a real swing high (58.5) and a real swing low (56.5), so a
    genuine position can open and later close. Bar 40 breaks out (BUY, enters position); bars
    41-46 hold above both pivots (no reversal, no re-fire); bar 47 crashes through the swing
    low AND back under the swing high in the same bar (SELL, closes position, and critically
    does not simultaneously re-fire BUY since price is now also back under the high pivot);
    bars 48-53 hold below (no further re-fire, now flat again).
    """
    rows = []
    for i in range(WARMUP_BARS):
        h = 58.5 if i % 5 == 2 else 58.0
        low = 56.5 if i % 5 == 2 else 57.0
        rows.append(_row(_date(i), 57.8, h, low, 57.8))
    rows.append(_row(_date(WARMUP_BARS), 61.0, 62.0, 60.5, 61.5))
    for i in range(WARMUP_BARS + 1, WARMUP_BARS + 7):
        rows.append(_row(_date(i), 61.0, 62.0 + i * 0.05, 60.5, 61.8))
    crash_i = WARMUP_BARS + 7
    rows.append(_row(_date(crash_i), 55.0, 55.0, 54.0, 54.5))
    for i in range(crash_i + 1, crash_i + 7):
        rows.append(_row(_date(i), 54.0, 55.0 - (i - crash_i) * 0.05, 54.0 - (i - crash_i) * 0.05, 54.2))
    return rows, crash_i


def _build_buy_dip_and_rebreak_rows():
    """40-bar warm-up confirms a real swing high (58.5) and swing low (56.5). Bar 40 breaks out
    (BUY, enters position). Bars 41-43 dip back UNDER the swing high (but stay above the swing
    low - no SELL) - so the raw buy condition goes false. Bars 44+ re-break above the swing high
    again while still in the same position (no SELL ever fired in between). A same-bar-vs-
    previous-bar edge trigger would incorrectly see this as a fresh false->true transition and
    re-fire BUY; the real in-position state machine must not, since the position never closed.
    """
    rows = []
    for i in range(WARMUP_BARS):
        h = 58.5 if i % 5 == 2 else 58.0
        low = 56.5 if i % 5 == 2 else 57.0
        rows.append(_row(_date(i), 57.8, h, low, 57.8))
    rows.append(_row(_date(WARMUP_BARS), 61.0, 62.0, 60.5, 61.5))  # BUY here
    dip_start = WARMUP_BARS + 1
    for i in range(dip_start, dip_start + 3):
        rows.append(_row(_date(i), 58.0, 58.0, 57.0, 57.5))  # dips under 58.5 high pivot, stays above 56.5 low pivot
    rebreak_start = dip_start + 3
    for i in range(rebreak_start, rebreak_start + 5):
        rows.append(_row(_date(i), 61.0, 62.5, 60.5, 62.0))  # re-breaks above 58.5 again, still no SELL ever fired
    return rows


class TestEdgeTriggeredSignals:
    def test_buy_fires_once_on_breakout_bar_not_every_subsequent_bar(self):
        rows = _build_breakout_and_hold_rows()
        gen = BuySignalGenerator()

        signals = gen.run("TEST", rows)

        post_warmup_buys = [s for s in signals if s["signal_type"] == "BUY" and s["date"] >= _date(WARMUP_BARS)]
        assert len(post_warmup_buys) == 1, (
            f"Expected exactly one BUY during/after the breakout bar, got {len(post_warmup_buys)} "
            f"on dates {[s['date'] for s in post_warmup_buys]} - price staying above an "
            f"already-broken pivot must not keep re-firing."
        )
        assert post_warmup_buys[0]["date"] == _date(WARMUP_BARS)

    def test_sell_never_fires_without_a_prior_position(self):
        """Matches the real Pine source exactly: `sellStudy = sellSignal and inPosition` - a
        breakdown with no open position behind it (no prior BUY) plots nothing at all, not a
        SELL. This is the opposite of the old (pre-2026-08-19) assumption that any breakdown
        should always emit a SELL.
        """
        rows = _build_breakdown_and_hold_rows()
        gen = BuySignalGenerator()

        signals = gen.run("TEST", rows)

        assert signals == [], (
            f"Expected zero signals - the breakdown never had a preceding BUY/open position, "
            f"so Pine's sellStudy=sellSignal-and-inPosition would never plot it. Got: "
            f"{[(s['signal_type'], s['date']) for s in signals]}"
        )

    def test_buy_then_sell_fires_once_each_not_every_subsequent_bar(self):
        rows, crash_i = _build_buy_then_breakdown_rows()
        gen = BuySignalGenerator()

        signals = gen.run("TEST", rows)

        buys = [s for s in signals if s["signal_type"] == "BUY"]
        sells = [s for s in signals if s["signal_type"] == "SELL"]
        assert len(buys) == 1 and buys[0]["date"] == _date(WARMUP_BARS), (
            f"Expected exactly one BUY on the breakout bar {_date(WARMUP_BARS)}, got {[b['date'] for b in buys]}"
        )
        assert len(sells) == 1 and sells[0]["date"] == _date(crash_i), (
            f"Expected exactly one SELL on the breakdown bar {_date(crash_i)} (the position was "
            f"genuinely open from the earlier BUY), got {[s['date'] for s in sells]}"
        )

    def test_buy_does_not_refire_after_dip_while_still_in_position(self):
        """Regression for the 2026-08-19 fix: a same-bar-vs-previous-bar edge trigger would
        wrongly re-fire BUY when the raw condition dips false then true again, even though no
        SELL ever closed the position in between. The real in-position state machine must
        suppress the second apparent breakout.
        """
        rows = _build_buy_dip_and_rebreak_rows()
        gen = BuySignalGenerator()

        signals = gen.run("TEST", rows)

        buys = [s for s in signals if s["signal_type"] == "BUY"]
        sells = [s for s in signals if s["signal_type"] == "SELL"]
        assert len(buys) == 1 and buys[0]["date"] == _date(WARMUP_BARS), (
            f"Expected exactly one BUY (the original breakout) with no re-fire after the dip "
            f"and re-break while still in the same position, got {[b['date'] for b in buys]}"
        )
        assert sells == [], f"No SELL condition was ever built into this scenario, got {[s['date'] for s in sells]}"
