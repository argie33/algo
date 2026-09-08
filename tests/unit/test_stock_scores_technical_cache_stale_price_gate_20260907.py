#!/usr/bin/env python3
"""Regression test: StockScoresLoader._prepare_batch_context's technical_cache (RSI/MACD/SMA,
read fresh from technical_data_daily each run) must not feed momentum_score a frozen snapshot
from a symbol whose price feed has gone dark, the same way momentum_metrics' own return-based
fields and Risk's volatility/beta already gate on staleness
(test_risk_metrics_momentum_stale_price_gate_20260901.py /
test_risk_metrics_stability_stale_price_gate_20260901.py).

Root cause (2026-09-07): `_prepare_batch_context` built `_technical_cache` with
`SELECT DISTINCT ON (symbol) ... FROM technical_data_daily ORDER BY symbol, date DESC` and no
check against the actual current date - unlike its two siblings. Live-confirmed still broken as
of this session: FBRX (acquired by argenx, delisted 2026-08-27 - the SAME symbol that motivated
the 2026-09-01 sibling fixes) still scored momentum_score=87.42 off its frozen 2026-08-26
RSI(84.4)/MACD/SMA readings, 8 trading days after its price feed went dark, because this third
sibling never got the same gate.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import STALE_PRICE_TRADING_DAYS_THRESHOLD, StockScoresLoader


def _db_context_mock(fetchall_side_effect: list, fetchone_return: tuple = (70.0,)) -> MagicMock:
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = fetchone_return
    mock_cur.fetchall.side_effect = fetchall_side_effect
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


def _run_prepare(now: datetime, technical_rows: list) -> StockScoresLoader:
    # Empty-list stand-ins for quality/growth/value/stability/liquidity/momentum (queried,
    # in order, before the technical_cache query this test actually cares about).
    fetchall_side_effect = [[], [], [], [], [], [], technical_rows]
    loader = StockScoresLoader()
    with (
        patch("loaders.load_stock_scores.DatabaseContext", return_value=_db_context_mock(fetchall_side_effect)),
        patch("loaders.load_stock_scores.datetime") as mock_dt,
    ):
        mock_dt.now.return_value = now
        loader._prepare_batch_context()
    return loader


class TestTechnicalCacheStalePriceGate:
    def test_stale_technical_row_excluded_from_cache(self):
        """FBRX-shaped case: last technical_data_daily row is 8 trading days old - must not
        be fed into momentum scoring as if current."""
        now = datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)
        technical_rows = [("FBRX", 84.39, 6.14, 52.36, 33.41, 76.99, date(2026, 8, 26))]

        loader = _run_prepare(now, technical_rows)

        assert "FBRX" not in loader._technical_cache

    def test_fresh_technical_row_still_included(self):
        """Same shape, but the latest row is recent - must NOT be gated."""
        now = datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)
        technical_rows = [("LIVE", 55.0, 1.2, 100.0, 95.0, 105.0, date(2026, 9, 4))]

        loader = _run_prepare(now, technical_rows)

        assert "LIVE" in loader._technical_cache
        assert loader._technical_cache["LIVE"] == (55.0, 1.2, 100.0, 95.0, 105.0)

    def test_gap_at_exactly_the_threshold_is_not_stale(self):
        """Boundary: exactly STALE_PRICE_TRADING_DAYS_THRESHOLD trading days old must still be
        included (the gate is a `>` check, not `>=`), matching the sibling gates' convention."""
        last_date = date(2026, 8, 26)
        now = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)  # 3 trading days forward (Fri->Mon)
        technical_rows = [("BOUNDARY", 55.0, 1.2, 100.0, 95.0, 105.0, last_date)]

        loader = _run_prepare(now, technical_rows)

        assert "BOUNDARY" in loader._technical_cache
