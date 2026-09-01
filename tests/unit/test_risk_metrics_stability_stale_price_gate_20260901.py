#!/usr/bin/env python3
"""Regression test: RiskMetricsLoader._compute_stability_row must not compute volatility/beta
off a frozen/stale last close as if it were current - the sibling gap to
_compute_momentum_row's stale-price gate (see test_risk_metrics_momentum_stale_price_gate_20260901.py),
now fixed on this method too.

Root cause (/goal session, 2026-09-01): live-confirmed on WBS (Webster Financial Corp, a real
actively-traded regional bank) ranking #4 in the Risk pillar (risk_score=91.68) and #4 in
Composite, off a price_daily feed frozen at 2026-08-19 - 13 trading days stale at the time of
this fix (known yfinance-outage gap, see avb_eqr_wbs_yfinance_gap_reverified_still_open_20260901
in memory). This method queried the most recent 252 price_daily rows with no check against the
actual current date, so a symbol whose price feed had gone silent kept having volatility/beta
computed from an increasingly stale window and reported as current risk.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from loaders.load_risk_metrics_daily import STALE_PRICE_TRADING_DAYS_THRESHOLD, RiskMetricsLoader


def _rows(n: int, last_date: date, price: float = 100.0) -> list[tuple[date, float, float]]:
    # 3-tuple (date, close, adj_close), most recent first (DESC) matching the real query shape.
    return [(last_date - timedelta(days=i), price + (i % 7), price + (i % 7)) for i in range(n)]


def _db_context_mock(price_rows, spy_rows, debt_to_assets=None):
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (debt_to_assets,) if debt_to_assets is not None else None
    mock_cur.fetchall.side_effect = [price_rows, spy_rows]
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    return mock_ctx


class TestStabilityStalePriceGate:
    def test_stale_price_marks_volatility_and_beta_unavailable(self):
        """WBS-shaped case: last real close is 13 trading days old - must not compute
        volatility/beta from it."""
        last_trade_date = date(2026, 8, 19)
        now = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
        rows = _rows(252, last_trade_date)
        spy_rows = _rows(252, date(2026, 9, 1))

        loader = RiskMetricsLoader()
        with (
            patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=_db_context_mock(rows, spy_rows)),
            patch("loaders.load_risk_metrics_daily.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = now
            result = loader._compute_stability_row("WBS")

        assert result["volatility_30d"] is None
        assert result["volatility_60d"] is None
        assert result["volatility_252d"] is None
        assert result["beta"] is None
        assert result["volatility_60d_unavailable_reason"] == "stale_price_data"
        assert result["beta_unavailable_reason"] == "stale_price_data"

    def test_stale_price_still_reports_debt_to_assets_if_available(self):
        """debt_to_assets is independent of price_daily - a stale price feed shouldn't
        discard it, same MINIMUM DATA REQUIREMENT convention this method already applies to
        every other partial-failure branch."""
        last_trade_date = date(2026, 8, 19)
        now = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
        rows = _rows(252, last_trade_date)
        spy_rows = _rows(252, date(2026, 9, 1))

        loader = RiskMetricsLoader()
        with (
            patch(
                "loaders.load_risk_metrics_daily.DatabaseContext",
                return_value=_db_context_mock(rows, spy_rows, debt_to_assets=0.42),
            ),
            patch("loaders.load_risk_metrics_daily.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = now
            result = loader._compute_stability_row("WBS")

        assert result["debt_to_assets"] == 0.42
        assert result["data_unavailable"] is False
        assert result["reason"] is None

    def test_fresh_price_still_computes_stability_normally(self):
        """Same shape, but the last close is today - must NOT be gated."""
        today = date(2026, 9, 1)
        now = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
        rows = _rows(252, today)
        spy_rows = _rows(252, today)

        loader = RiskMetricsLoader()
        with (
            patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=_db_context_mock(rows, spy_rows)),
            patch("loaders.load_risk_metrics_daily.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = now
            result = loader._compute_stability_row("LIVE")

        assert result["volatility_60d"] is not None
        assert result["volatility_60d_unavailable_reason"] is None

    def test_gap_at_exactly_the_threshold_is_not_stale(self):
        """Boundary: exactly STALE_PRICE_TRADING_DAYS_THRESHOLD trading days old must still
        compute (the gate is a `>` check, not `>=`)."""
        last_trade_date = date(2026, 8, 26)
        now = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)  # 3 trading days forward, skipping the weekend
        rows = _rows(252, last_trade_date)
        spy_rows = _rows(252, date(2026, 8, 31))

        loader = RiskMetricsLoader()
        with (
            patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=_db_context_mock(rows, spy_rows)),
            patch("loaders.load_risk_metrics_daily.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = now
            result = loader._compute_stability_row("BOUNDARY")

        assert result["volatility_60d"] is not None
        assert result["volatility_60d_unavailable_reason"] is None
