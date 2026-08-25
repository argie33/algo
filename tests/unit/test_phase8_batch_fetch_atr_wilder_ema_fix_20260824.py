#!/usr/bin/env python3
"""Regression test for the 2026-08-24 fix to _batch_fetch_technical_data's ATR fallback (see
[[batch_fetch_atr_methodology_mismatch_found_20260824]] in memory for the original finding).

Before this fix, the fallback (fires when Phase 5's precomputed atr_14 is missing for a symbol)
computed ATR as a flat SMA of True Range - a documented methodology mismatch against
loaders/technical_indicators.py's compute_atr(), which uses Wilder's exponential smoothing and
whose own docstring explicitly warns against exactly the SMA approach the old fallback used.

The fix reuses compute_atr() directly rather than reimplementing Wilder smoothing in SQL.
Empirically validated (2026-08-24, not reproduced here) against 9 real symbols in
technical_data_daily: 8/9 matched to within 0.04%. This test instead locks in the INTEGRATION
correctness (DataFrame construction, per-symbol grouping, final-value extraction, insufficient-
history skip) against a synthetic OHLC series with a known expected value, computed via the same
compute_atr() call this code uses - proving the glue code is wired correctly, not re-deriving
Wilder's math itself (already-trusted, existing code).
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from algo.orchestrator.phase8_entry_execution import _batch_fetch_technical_data
from loaders.technical_indicators import compute_atr


def _synthetic_ohlc_rows(symbol: str, n_days: int, run_date: date, base: float = 100.0) -> list[tuple]:
    """A synthetic, deterministic OHLC series: alternating small daily ranges around a slow
    uptrend, so True Range (and therefore ATR) is well-defined and non-trivial. `base` varies
    the whole series (not just a seed) so two symbols produce genuinely different ATR values."""
    rows = []
    d = run_date - timedelta(days=n_days - 1)
    range_mult = base / 100.0  # scale the daily range with price level, like a real symbol would
    for i in range(n_days):
        drift = i * 0.05 * range_mult
        high = base + drift + (2.0 if i % 2 == 0 else 1.0) * range_mult
        low = base + drift - (1.0 if i % 2 == 0 else 2.0) * range_mult
        close = base + drift
        rows.append((symbol, d, high, low, close))
        d += timedelta(days=1)
    return rows


def _expected_atr(rows: list[tuple], period: int = 14) -> float:
    df = pd.DataFrame(rows, columns=["symbol", "date", "high", "low", "close"])
    series = compute_atr(df["high"].astype(float), df["low"].astype(float), df["close"].astype(float), period)
    return float(series.iloc[-1])


class TestBatchFetchTechnicalDataATRFix:
    def test_atr_matches_direct_compute_atr_call(self):
        """The fallback's computed ATR for a symbol must exactly match calling compute_atr()
        directly on the same OHLC series - proves the integration (grouping, sorting, final-
        value extraction) is wired correctly."""
        run_date = date(2026, 8, 24)
        rows = _synthetic_ohlc_rows("SYNTH", 100, run_date)
        expected = _expected_atr(rows)

        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_db:
            mock_cur = MagicMock()
            # First execute(): sma_50/close query. Second execute(): OHLC history query.
            mock_cur.fetchall.side_effect = [
                [{"symbol": "SYNTH", "sma_50": 101.5, "close": rows[-1][4]}],
                rows,
            ]
            mock_db.return_value.__enter__.return_value = mock_cur

            result = _batch_fetch_technical_data({"SYNTH": {"sma_50": None, "atr_14": None, "close": None}}, run_date)

        assert "SYNTH" in result
        assert result["SYNTH"]["atr"] == pytest.approx(expected, rel=1e-9)

    def test_symbol_with_insufficient_history_is_skipped_not_crashed(self):
        """Fewer than `period` rows of history for a symbol must be gracefully skipped
        (same as the old fallback's implicit behavior), not crash the whole batch."""
        run_date = date(2026, 8, 24)
        thin_rows = _synthetic_ohlc_rows("THIN", 5, run_date)  # < period=14

        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchall.side_effect = [
                [{"symbol": "THIN", "sma_50": 101.0, "close": thin_rows[-1][4]}],
                thin_rows,
            ]
            mock_db.return_value.__enter__.return_value = mock_cur

            result = _batch_fetch_technical_data({"THIN": {"sma_50": None, "atr_14": None, "close": None}}, run_date)

        assert "THIN" not in result

    def test_multiple_symbols_computed_independently(self):
        """Two symbols in the same batch must each get their own correctly-grouped ATR, not
        a value contaminated by the other symbol's rows."""
        run_date = date(2026, 8, 24)
        rows_a = _synthetic_ohlc_rows("AAA", 100, run_date, base=100.0)
        rows_b = _synthetic_ohlc_rows("BBB", 100, run_date, base=250.0)
        expected_a = _expected_atr(rows_a)
        expected_b = _expected_atr(rows_b)

        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchall.side_effect = [
                [
                    {"symbol": "AAA", "sma_50": 101.5, "close": rows_a[-1][4]},
                    {"symbol": "BBB", "sma_50": 251.5, "close": rows_b[-1][4]},
                ],
                rows_a + rows_b,
            ]
            mock_db.return_value.__enter__.return_value = mock_cur

            result = _batch_fetch_technical_data(
                {
                    "AAA": {"sma_50": None, "atr_14": None, "close": None},
                    "BBB": {"sma_50": None, "atr_14": None, "close": None},
                },
                run_date,
            )

        assert result["AAA"]["atr"] == pytest.approx(expected_a, rel=1e-9)
        assert result["BBB"]["atr"] == pytest.approx(expected_b, rel=1e-9)
        assert result["AAA"]["atr"] != result["BBB"]["atr"]
