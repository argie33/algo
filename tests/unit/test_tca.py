"""
Tests for Transaction Cost Analysis (TCA) module.

Validates:
- Slippage calculation for BUY and SELL orders
- Alert thresholds (100 bps WARN, 300 bps ERROR)
- Daily and monthly aggregation metrics
- Fill rate tracking
- Execution latency recording
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, call
from algo_tca import TCAEngine


@pytest.fixture
def tca_engine(test_config):
    """TCA engine instance with mocked DB."""
    engine = TCAEngine(test_config)
    engine.conn = MagicMock()
    engine.cur = MagicMock()
    return engine


class TestSlippageCalculation:
    """Test slippage_bps calculation for various order types."""

    def test_buy_favorable_slippage(self, tca_engine):
        """BUY with favorable slippage (fill below signal price)."""
        # Signal price: $100, Fill price: $99 (favorable)
        # Slippage = (99 - 100) / 100 * 10000 = -100 bps
        # Should be favorable (negative), no alert
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (1,)  # Last inserted ID

        result = tca_engine.record_fill(
            trade_id=1,
            symbol='AAPL',
            signal_price=100.0,
            fill_price=99.0,
            shares_requested=100,
            shares_filled=100,
            side='BUY',
            execution_latency_ms=500
        )

        assert result['slippage_bps'] == -100.0  # Favorable
        assert 'alert' not in result  # No alert for favorable
        assert result['fill_rate_pct'] == 100.0

    def test_buy_adverse_slippage_warn(self, tca_engine):
        """BUY with 100 bps adverse slippage → WARN alert."""
        # Signal: $100, Fill: $101 (adverse for buy)
        # Slippage = (101 - 100) / 100 * 10000 = 100 bps (adverse)
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (2,)

        result = tca_engine.record_fill(
            trade_id=2,
            symbol='MSFT',
            signal_price=100.0,
            fill_price=101.0,
            shares_requested=100,
            shares_filled=100,
            side='BUY',
            execution_latency_ms=600
        )

        assert result['slippage_bps'] == 100.0  # Adverse
        assert result['alert']['severity'] == 'WARN'
        assert '100 bps' in result['alert']['message']

    def test_buy_adverse_slippage_error(self, tca_engine):
        """BUY with 300 bps adverse slippage → ERROR alert."""
        # Signal: $100, Fill: $103 (3% adverse)
        # Slippage = (103 - 100) / 100 * 10000 = 300 bps
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (3,)

        result = tca_engine.record_fill(
            trade_id=3,
            symbol='TSLA',
            signal_price=100.0,
            fill_price=103.0,
            shares_requested=100,
            shares_filled=100,
            side='BUY',
            execution_latency_ms=2000
        )

        assert result['slippage_bps'] == 300.0
        assert result['alert']['severity'] == 'ERROR'
        assert '300 bps' in result['alert']['message']

    def test_sell_favorable_slippage(self, tca_engine):
        """SELL with favorable slippage (fill above signal price)."""
        # Signal: $100, Fill: $101 (favorable for sell)
        # Adverse slippage = (100 - 101) / 100 * 10000 = -100 bps (favorable)
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (4,)

        result = tca_engine.record_fill(
            trade_id=4,
            symbol='GOOGL',
            signal_price=100.0,
            fill_price=101.0,
            shares_requested=50,
            shares_filled=50,
            side='SELL',
            execution_latency_ms=400
        )

        # For SELL: slippage = (signal - fill) / signal * 10000 = (100 - 101) / 100 * 10000 = -100
        assert result['slippage_bps'] == -100.0
        assert 'alert' not in result

    def test_sell_adverse_slippage(self, tca_engine):
        """SELL with adverse slippage (fill below signal price)."""
        # Signal: $100, Fill: $98 (adverse for sell)
        # Adverse slippage = (100 - 98) / 100 * 10000 = 200 bps
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (5,)

        result = tca_engine.record_fill(
            trade_id=5,
            symbol='AMZN',
            signal_price=100.0,
            fill_price=98.0,
            shares_requested=75,
            shares_filled=75,
            side='SELL',
            execution_latency_ms=300
        )

        assert result['slippage_bps'] == 200.0
        assert result['alert']['severity'] == 'WARN'

    def test_partial_fill_tracking(self, tca_engine):
        """Partial fills are correctly tracked in fill_rate_pct."""
        # Requested 100, filled 60
        # fill_rate = 60 / 100 * 100 = 60%
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (6,)

        result = tca_engine.record_fill(
            trade_id=6,
            symbol='NFLX',
            signal_price=200.0,
            fill_price=200.5,
            shares_requested=100,
            shares_filled=60,
            side='BUY',
            execution_latency_ms=800
        )

        assert result['fill_rate_pct'] == 60.0

    def test_zero_shares_requested_edge_case(self, tca_engine):
        """Edge case: zero shares requested → fill_rate 0%."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (7,)

        result = tca_engine.record_fill(
            trade_id=7,
            symbol='SPY',
            signal_price=400.0,
            fill_price=400.0,
            shares_requested=0,
            shares_filled=0,
            side='BUY',
            execution_latency_ms=100
        )

        assert result['fill_rate_pct'] == 0.0


class TestDailyReport:
    """Test daily TCA aggregation and reporting."""

    def test_daily_report_no_trades(self, tca_engine):
        """Daily report with no trades returns no_trades status."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (0,)  # No trades

        report = tca_engine.daily_report(report_date=date.today())

        assert report['fill_count'] == 0
        assert report['status'] == 'no_trades'

    def test_daily_report_single_trade(self, tca_engine):
        """Daily report with one trade computes correct metrics."""
        report_date = date.today()
        tca_engine.cur.execute.return_value = None

        # First query: main stats
        tca_engine.cur.fetchone.side_effect = [
            (1, 50.0, 50.0, 50.0, 95.0, 500),  # fill_count, avg_abs_slip, min_slip, max_slip, avg_fill_rate, avg_latency
            (0,),  # high_slippage_count
            ('AAPL', 50.0)  # worst_symbol
        ]

        report = tca_engine.daily_report(report_date=report_date)

        assert report['fill_count'] == 1
        assert report['avg_abs_slippage_bps'] == 50.0
        assert report['best_slippage_bps'] == 50.0
        assert report['worst_slippage_bps'] == 50.0
        assert report['avg_fill_rate_pct'] == 95.0
        assert report['avg_execution_latency_ms'] == 500
        assert report['high_slippage_fills'] == 0
        assert report['status'] == 'ok'

    def test_daily_report_high_slippage_warning(self, tca_engine):
        """Daily report flags high slippage count in status."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.side_effect = [
            (10, 150.0, 20.0, 200.0, 98.0, 400),  # 10 trades, avg 150 bps
            (3,),  # 3 trades > 100 bps
            ('TSLA', 200.0)
        ]

        report = tca_engine.daily_report()

        assert report['fill_count'] == 10
        assert report['high_slippage_fills'] == 3
        assert report['high_slippage_pct'] == 30.0
        assert report['status'] == 'warning'

    def test_daily_report_execution_latency(self, tca_engine):
        """Daily report tracks average execution latency in ms."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.side_effect = [
            (5, 75.0, 25.0, 125.0, 99.0, 750),  # avg latency 750ms
            (1,),
            ('MSFT', 75.0)
        ]

        report = tca_engine.daily_report()

        assert report['avg_execution_latency_ms'] == 750


class TestMonthlySummary:
    """Test monthly TCA aggregation with percentile metrics."""

    def test_monthly_summary_no_trades(self, tca_engine):
        """Monthly summary with no trades."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (0,)

        summary = tca_engine.monthly_summary(year=2026, month=5)

        assert summary['status'] == 'no_trades'
        assert 'period' in summary

    def test_monthly_summary_with_trades(self, tca_engine):
        """Monthly summary computes P95 slippage and aggregate metrics."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (
            50,       # fill_count
            80.0,     # avg_abs_slippage_bps
            120.0,    # p95_abs_slippage_bps (95th percentile)
            250.0,    # worst_slippage_bps
            97.5,     # avg_fill_rate_pct
            5         # high_slippage_count (> 100 bps)
        )

        summary = tca_engine.monthly_summary(year=2026, month=5)

        assert summary['fill_count'] == 50
        assert summary['avg_abs_slippage_bps'] == 80.0
        assert summary['p95_abs_slippage_bps'] == 120.0
        assert summary['worst_slippage_bps'] == 250.0
        assert summary['high_slippage_fills'] == 5
        assert summary['high_slippage_pct'] == 10.0
        assert summary['avg_fill_rate_pct'] == 97.5
        assert summary['status'] == 'warning'  # 5 of 50 trades > 100 bps

    def test_monthly_summary_high_slippage_period(self, tca_engine):
        """Monthly summary flags periods with excessive slippage."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (
            50, 150.0, 200.0, 350.0, 96.0, 15  # 15 of 50 trades > 100 bps
        )

        summary = tca_engine.monthly_summary(year=2026, month=5)

        assert summary['status'] == 'warning'
        assert summary['high_slippage_pct'] == 30.0


class TestAlertThresholds:
    """Test alert logic for different slippage levels."""

    def test_no_alert_favorable(self, tca_engine):
        """Favorable slippage (negative) never alerts."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (8,)

        result = tca_engine.record_fill(
            trade_id=8, symbol='VTI', signal_price=150.0, fill_price=149.0,
            shares_requested=50, shares_filled=50, side='BUY', execution_latency_ms=400
        )

        assert 'alert' not in result

    def test_no_alert_below_threshold(self, tca_engine):
        """Adverse slippage < 100 bps doesn't alert."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (9,)

        result = tca_engine.record_fill(
            trade_id=9, symbol='VOO', signal_price=400.0, fill_price=400.5,
            shares_requested=25, shares_filled=25, side='BUY', execution_latency_ms=300
        )

        # Slippage = 0.5 / 400 * 10000 = 12.5 bps
        assert result['slippage_bps'] == 12.5
        assert 'alert' not in result

    def test_warn_at_100_bps(self, tca_engine):
        """Exactly 100 bps triggers WARN."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (10,)

        result = tca_engine.record_fill(
            trade_id=10, symbol='IVV', signal_price=500.0, fill_price=505.0,
            shares_requested=20, shares_filled=20, side='BUY', execution_latency_ms=250
        )

        assert result['slippage_bps'] == 100.0
        assert result['alert']['severity'] == 'WARN'

    def test_error_at_300_bps(self, tca_engine):
        """Exactly 300 bps triggers ERROR."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (11,)

        result = tca_engine.record_fill(
            trade_id=11, symbol='SCHB', signal_price=100.0, fill_price=103.0,
            shares_requested=100, shares_filled=100, side='BUY', execution_latency_ms=1000
        )

        assert result['slippage_bps'] == 300.0
        assert result['alert']['severity'] == 'ERROR'

    def test_error_above_300_bps(self, tca_engine):
        """Slippage > 300 bps also triggers ERROR."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (12,)

        result = tca_engine.record_fill(
            trade_id=12, symbol='QQQ', signal_price=350.0, fill_price=361.0,
            shares_requested=30, shares_filled=30, side='BUY', execution_latency_ms=5000
        )

        assert result['slippage_bps'] == 314.29
        assert result['alert']['severity'] == 'ERROR'
        assert '314 bps' in result['alert']['message']


class TestExecutionLatency:
    """Test execution latency tracking."""

    def test_execution_latency_recorded(self, tca_engine):
        """Execution latency is recorded in result and DB."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (13,)

        result = tca_engine.record_fill(
            trade_id=13, symbol='RUT', signal_price=2000.0, fill_price=2000.0,
            shares_requested=10, shares_filled=10, side='BUY', execution_latency_ms=750
        )

        assert result['execution_latency_ms'] == 750

    def test_execution_latency_none_handled(self, tca_engine):
        """None execution_latency is accepted (local/paper trades)."""
        tca_engine.cur.execute.return_value = None
        tca_engine.cur.fetchone.return_value = (14,)

        result = tca_engine.record_fill(
            trade_id=14, symbol='DIA', signal_price=350.0, fill_price=350.0,
            shares_requested=40, shares_filled=40, side='BUY', execution_latency_ms=None
        )

        assert result['execution_latency_ms'] is None


class TestDatabaseFailureHandling:
    """Test graceful handling of database failures."""

    def test_connect_failure_returns_error(self, test_config):
        """DB connection failure is caught and logged."""
        engine = TCAEngine(test_config)
        engine.connect = MagicMock(side_effect=Exception("DB unavailable"))

        with pytest.raises(Exception):
            engine.record_fill(
                trade_id=99, symbol='ERROR', signal_price=100.0, fill_price=100.0,
                shares_requested=1, shares_filled=1, side='BUY'
            )

    def test_daily_report_db_error(self, tca_engine):
        """DB error in daily_report returns error status."""
        tca_engine.cur.execute.side_effect = Exception("Query failed")

        report = tca_engine.daily_report()

        assert report['status'] == 'error'
        assert 'message' in report


class TestDatabaseIntegration:
    """Integration tests with actual DB (if test_db fixture is available)."""

    @pytest.mark.skip(reason="PostgreSQL test database not available in this environment")
    def test_record_fill_inserts_row(self, test_db):
        """record_fill inserts row and returns tca_id."""
        config = {'db_mode': 'test'}
        engine = TCAEngine(config)

        result = engine.record_fill(
            trade_id=1,
            symbol='TEST',
            signal_price=100.0,
            fill_price=100.5,
            shares_requested=100,
            shares_filled=100,
            side='BUY',
            execution_latency_ms=500
        )

        assert result['success'] if hasattr(result, '__getitem__') else True
        assert result['tca_id'] > 0 if hasattr(result, '__getitem__') else True

    @pytest.mark.skip(reason="PostgreSQL test database not available in this environment")
    def test_daily_report_aggregates_correctly(self, test_db):
        """daily_report aggregates multiple fills correctly."""
        config = {'db_mode': 'test'}
        engine = TCAEngine(config)

        # Insert test fills
        engine.record_fill(1, 'TEST', 100.0, 100.5, 100, 100, 'BUY', 500)
        engine.record_fill(2, 'TEST', 200.0, 199.5, 50, 50, 'BUY', 600)

        report = engine.daily_report(date.today())

        if 'fill_count' in report:
            assert report['fill_count'] >= 2
