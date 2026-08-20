#!/usr/bin/env python3
"""Cross-checks algo/signals/buy_signal_generator.py::BuySignalGenerator against
pine_reference_impl.py, an independent, from-scratch translation of the user's actual
TradingView Pine Script v4 source ("Breakout Trend Follower" by @millerrh, provided
2026-08-19). The two implementations were written separately from the same specification;
agreement between them is stronger evidence of Pine-fidelity than either one read in
isolation.

Live-verified 2026-08-19 against the full local symbol universe (5,133 real symbols with
sufficient technical_data_daily/price_daily history): zero signal-level mismatches. This test
covers the same comparison with synthetic data so it runs in CI without a database.
"""

import random

from algo.signals.buy_signal_generator import BuySignalGenerator
from tests.unit.pine_reference_impl import pine_reference_signals


def _random_walk_rows(seed: int, n: int = 300, start_price: float = 100.0) -> list[dict]:
    """Deterministic (seeded) random-walk OHLCV series with a trailing SMA50, generating
    realistic swing highs/lows, breakouts, breakdowns, and trend changes without any
    hand-tuned scenario - broader, less biased coverage than the hand-built fixtures in
    test_buy_signal_generator_edge_triggered.py.
    """
    rng = random.Random(seed)
    closes = [start_price]
    for _ in range(n - 1):
        pct = rng.uniform(-0.03, 0.031)  # slight upward bias, matches typical trending data
        closes.append(max(1.0, closes[-1] * (1 + pct)))

    rows = []
    for i, close in enumerate(closes):
        intraday = close * rng.uniform(0.005, 0.025)
        high = close + rng.uniform(0, intraday)
        low = close - rng.uniform(0, intraday)
        open_ = low + rng.uniform(0, high - low) if high > low else close
        window = closes[max(0, i - 49) : i + 1]
        sma_50 = sum(window) / len(window)
        rows.append(
            {
                "date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "sma_50": sma_50,
                "sma_200": sma_50,  # not used by either implementation's trigger logic
                "volume": 1_000_000,
                "atr": 1.0,
                "rsi": 50.0,
                "macd": 0.0,
                "macd_signal": 0.0,
                "ema_21": close,
                "adx": 25.0,
                "mansfield_rs": 0.0,
            }
        )
    return rows


class TestMatchesPineReference:
    def test_random_walks_match_pine_reference_exactly(self):
        """20 independent seeded random walks - if the production port has drifted from the
        real Pine logic in any way the hand-built fixtures don't happen to exercise, a broad
        random sweep is far more likely to surface it than a handful of scripted scenarios.
        """
        gen = BuySignalGenerator()
        mismatches = []

        for seed in range(20):
            rows = _random_walk_rows(seed)
            prod_signals = gen.run("TEST", rows)
            prod_set = {(s["date"], s["signal_type"]) for s in prod_signals}

            ref_signals = pine_reference_signals(rows)
            ref_set = {(s["date"], s["signal"]) for s in ref_signals}

            if prod_set != ref_set:
                mismatches.append(
                    {
                        "seed": seed,
                        "prod_only": sorted(prod_set - ref_set),
                        "ref_only": sorted(ref_set - prod_set),
                    }
                )

        assert not mismatches, (
            f"Production signal generation diverged from the independent Pine reference "
            f"implementation on {len(mismatches)}/20 random walks: {mismatches}"
        )
