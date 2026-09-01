#!/usr/bin/env python3
"""Regression test: RiskMetricsLoader._compute_momentum_row must not compute momentum off a
frozen/stale last close as if it were current.

Root cause (/goal session, 2026-09-01): FBRX (Forte Biosciences) was acquired by argenx via a
$77/share tender offer that completed 2026-08-27 (8-K on file: item_2_01 Completion of
Acquisition + item_3_01 Notice of Delisting, both true) - real trading stopped after
2026-08-26's close. `_compute_momentum_row` set `today = sorted_dates[-1]` (whatever the
symbol's own latest price_daily row happened to be) with no check against the actual current
date, so a symbol whose price feed had gone silent kept having its last real close treated as
"current" forever - momentum/ROC computed off an increasingly stale window. Live-confirmed
result: FBRX ranked #1 in Momentum (roc_60d=303%, roc_252d=331%) five calendar days after it
stopped trading, with data_unavailable=False and no flag anywhere.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from loaders.load_risk_metrics_daily import STALE_PRICE_TRADING_DAYS_THRESHOLD, RiskMetricsLoader


def _price_rows(n: int, last_date: date, price: float = 100.0) -> list[tuple[date, float, float]]:
    # 3-tuple (date, close, adj_close), most recent first (DESC) matching the real
    # `ORDER BY date DESC` query shape.
    return [(last_date - timedelta(days=i), price, price) for i in range(n)]


def _db_context_mock(rows: list[tuple[date, float, float]]) -> MagicMock:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    return mock_ctx


class TestMomentumStalePriceGate:
    def test_stale_price_marks_data_unavailable_not_computed(self):
        """FBRX-shaped case: last real close is 4 trading days old (2026-08-26 -> 2026-09-01,
        crossing one weekend) - must not compute momentum from it."""
        last_trade_date = date(2026, 8, 26)
        now = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
        rows = _price_rows(60, last_trade_date)

        loader = RiskMetricsLoader()
        with (
            patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=_db_context_mock(rows)),
            patch("loaders.load_risk_metrics_daily.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = now
            result = loader._compute_momentum_row("FBRX")

        assert result["data_unavailable"] is True
        assert "stale" in result["reason"].lower()
        assert result["momentum_1m"] is None
        assert result["momentum_12m"] is None

    def test_fresh_price_still_computes_momentum_normally(self):
        """Same shape, but the last close is today - must NOT be gated."""
        last_trade_date = date(2026, 9, 1)
        now = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
        rows = _price_rows(260, last_trade_date, price=100.0)

        loader = RiskMetricsLoader()
        with (
            patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=_db_context_mock(rows)),
            patch("loaders.load_risk_metrics_daily.datetime") as mock_dt,
            patch.object(RiskMetricsLoader, "_fetch_technical_indicators", return_value={}),
        ):
            mock_dt.now.return_value = now
            result = loader._compute_momentum_row("LIVE")

        assert result["data_unavailable"] is False
        assert result["momentum_1m"] is not None

    def test_gap_at_exactly_the_threshold_is_not_stale(self):
        """Boundary: exactly STALE_PRICE_TRADING_DAYS_THRESHOLD trading days old must still
        compute (the gate is a `>` check, not `>=`) - a normal short pipeline-timing gap
        shouldn't get flagged."""
        last_trade_date = date(2026, 8, 26)
        # Walk forward exactly STALE_PRICE_TRADING_DAYS_THRESHOLD trading days from
        # last_trade_date (skipping the Aug 29-30 weekend).
        trading_days_forward = [
            date(2026, 8, 27),
            date(2026, 8, 28),
            date(2026, 8, 31),
        ]
        assert len(trading_days_forward) == STALE_PRICE_TRADING_DAYS_THRESHOLD
        now = datetime.combine(trading_days_forward[-1], datetime.min.time(), tzinfo=timezone.utc)
        rows = _price_rows(260, last_trade_date, price=100.0)

        loader = RiskMetricsLoader()
        with (
            patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=_db_context_mock(rows)),
            patch("loaders.load_risk_metrics_daily.datetime") as mock_dt,
            patch.object(RiskMetricsLoader, "_fetch_technical_indicators", return_value={}),
        ):
            mock_dt.now.return_value = now
            result = loader._compute_momentum_row("BOUNDARY")

        assert result["data_unavailable"] is False
