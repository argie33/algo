#!/usr/bin/env python3
"""Regression test for the 2026-08-18 edge-trigger fix in
algo/signals/buy_signal_generator.py::BuySignalGenerator.run().

Root cause of live signals no longer matching TradingView Pine Script: this loader emitted
a new BUY/SELL row every single day a stock remained beyond its swing pivot, instead of once
on the bar the breakout/breakdown actually happened (Pine's ta.crossover/ta.crossunder mark
only the crossing bar). Live audit against the DB on 2026-08-17 found 73% of that day's BUY
rows and 64% of its SELL rows were re-fires of a condition already true the day before, not
fresh crossovers - which is why a stock could sit flagged BUY or SELL for a week+ straight
while TradingView showed one clean mark.

These tests build a synthetic series with a warm-up sawtooth (establishing a real, strategy-1
swing pivot the normal way, not via the no-history fallback), then a clean breakout/breakdown
that holds for 7 more bars without ever reversing, and assert exactly one signal fires during
the hold period - the crossing bar itself, not one per bar spent beyond the pivot.

Note: day 1 of any brand-new series always produces one signal from the "not enough history
yet" fallback tier (see BuySignalGenerator._find_swing_high/_find_swing_low strategy 3) - the
same thing a real newly-listed symbol would show on its first eligible day. That's expected
and orthogonal to what's under test here, so assertions scope to the post-warm-up period.
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
    """Mirror image: 40-bar sawtooth warm-up pins a real swing low at 59.5, bar 40 breaks
    down to 56.0 and price keeps falling for 7 more bars without reclaiming the pivot.
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

    def test_sell_fires_once_on_breakdown_bar_not_every_subsequent_bar(self):
        rows = _build_breakdown_and_hold_rows()
        gen = BuySignalGenerator()

        signals = gen.run("TEST", rows)

        post_warmup_sells = [s for s in signals if s["signal_type"] == "SELL" and s["date"] >= _date(WARMUP_BARS)]
        assert len(post_warmup_sells) == 1, (
            f"Expected exactly one SELL during/after the breakdown bar, got {len(post_warmup_sells)} "
            f"on dates {[s['date'] for s in post_warmup_sells]} - price staying below an "
            f"already-broken pivot must not keep re-firing."
        )
        assert post_warmup_sells[0]["date"] == _date(WARMUP_BARS)
