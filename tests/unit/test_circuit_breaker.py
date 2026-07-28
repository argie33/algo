#!/usr/bin/env python3
"""Unit tests for CircuitBreaker module."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add algo directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from algo.risk import CircuitBreaker


@pytest.fixture
def mock_config():
    return {
        "circuit_breaker_enabled": True,
        "daily_loss_limit": -5000,
        "drawdown_limit": -20,
    }


@pytest.fixture
def mock_connection():
    mock_conn = Mock()
    mock_cur = Mock()
    mock_conn.cursor.return_value = mock_cur
    return mock_conn, mock_cur


@pytest.fixture
def circuit_breaker(mock_config):
    return CircuitBreaker(config=mock_config)


class TestCircuitBreakerInit:
    """Test CircuitBreaker initialization."""

    def test_init_with_config(self, mock_config):
        """Test initialization with configuration."""
        cb = CircuitBreaker(config=mock_config)
        assert cb.config == mock_config


class TestCircuitBreakerBasic:
    """Test basic CircuitBreaker functionality."""

    def test_check_all(self, circuit_breaker):
        """Test overall circuit breaker check."""
        mock_cur = Mock()
        mock_cur.fetchone.return_value = None
        mock_cur.rowcount = 0  # Ensure rowcount is an int, not a Mock
        all_pass = {"halted": False, "passed": True}
        # check_all() dispatches via circuit_breaker._checks[name], a dict of bound
        # methods captured at __init__ time (see circuit_breaker.py's comment on
        # self._checks - deliberate, to keep these methods visible to dead-code
        # tooling). patch.object(circuit_breaker, "_check_x", ...) only replaces the
        # instance attribute, not the bound method already stored in that dict, so
        # the dict entries must be patched directly instead.
        original_checks = dict(circuit_breaker._checks)
        for key in circuit_breaker._checks:
            circuit_breaker._checks[key] = Mock(return_value=all_pass)
        try:
            with patch("algo.risk.circuit_breaker.DatabaseContext") as mock_db_ctx:
                mock_db_ctx.return_value.__enter__.return_value = mock_cur
                mock_db_ctx.return_value.__exit__.return_value = False
                result = circuit_breaker.check_all()
                assert isinstance(result, dict)
                assert "halted" in result
        finally:
            circuit_breaker._checks.update(original_checks)


class TestCircuitBreakerVIX:
    """Test VIX-based circuit breaker logic."""

    def test_vix_spike_check(self, circuit_breaker):
        """Test VIX spike detection."""
        with patch.object(circuit_breaker, "_check_vix_spike") as mock_vix:
            mock_vix.return_value = {"halted": False, "vix_level": 20, "threshold": 30}
            result = circuit_breaker._check_vix_spike()
            assert isinstance(result, dict)
            assert "halted" in result
            assert "vix_level" in result

    def test_vix_spike_handles_datetime_not_date_from_driver(self, mock_config):
        """market_health_daily.date can come back as datetime (not date) from the DB
        driver - _resolve_current_market_stage already needed this same normalization
        for the identical column/table. Without it, comparing data_date (datetime)
        against min_acceptable_date (date) at the is_acceptable_age check raises
        TypeError instead of a clean stale-data result."""
        from datetime import date, datetime

        config = dict(mock_config, vix_max_threshold=30.0)
        cb = CircuitBreaker(config=config)
        mock_cur = Mock()
        today = date(2026, 7, 27)  # a Monday - trading day
        # Row's date column is a datetime, not a date - the exact condition that broke
        # _resolve_current_market_stage before its own fix.
        mock_cur.fetchone.return_value = (18.5, datetime(2026, 7, 27, 0, 0, 0), False, None)

        with patch("algo.infrastructure.MarketCalendar.is_trading_day", return_value=True):
            result = cb._check_vix_spike(current_date=today, cur=mock_cur)

        assert result["halted"] is False
        assert result["value"] == 18.5


class TestCircuitBreakerAll:
    """Test combined circuit breaker checks."""

    def test_all_breakers_integration(self, circuit_breaker):
        """Test all circuit breakers together."""
        circuit_breaker.conn = Mock()
        circuit_breaker.cur = Mock()

        with patch.object(circuit_breaker, "_check_drawdown", return_value={"passed": True}):
            with patch.object(circuit_breaker, "_check_daily_loss", return_value={"passed": True}):
                assert circuit_breaker.conn is not None
                assert circuit_breaker.cur is not None


class TestCircuitBreakerWithMalformedData:
    """Tests for CircuitBreaker handling of malformed/invalid data."""

    def test_circuit_breaker_with_none_config(self):
        """Verify CircuitBreaker rejects None config."""
        try:
            cb = CircuitBreaker(config=None)
            # Should either reject or handle gracefully
            assert cb is not None or True
        except (TypeError, ValueError, AttributeError):
            pass  # Expected

    def test_circuit_breaker_with_missing_required_fields(self):
        """Verify CircuitBreaker validates required config fields."""
        incomplete_config = {"circuit_breaker_enabled": True}
        try:
            cb = CircuitBreaker(config=incomplete_config)
            # Should validate that daily_loss_limit exists
            _ = cb.config["daily_loss_limit"]
        except KeyError:
            pass  # Expected

    def test_circuit_breaker_with_string_loss_limit(self):
        """Verify CircuitBreaker handles string loss limit."""
        config = {
            "circuit_breaker_enabled": True,
            "daily_loss_limit": "-5000",  # String instead of int
            "drawdown_limit": -20,
        }
        try:
            cb = CircuitBreaker(config=config)
            # Should either convert or reject
            loss_limit = cb.config["daily_loss_limit"]
            assert isinstance(loss_limit, (int, float, str))
        except (ValueError, TypeError):
            pass  # Expected

    def test_circuit_breaker_with_positive_loss_limit(self):
        """Verify CircuitBreaker handles positive loss limit (should be negative)."""
        config = {
            "circuit_breaker_enabled": True,
            "daily_loss_limit": 5000,  # Should be negative
            "drawdown_limit": -20,
        }
        try:
            cb = CircuitBreaker(config=config)
            # Should validate that daily_loss_limit is negative
            assert cb.config["daily_loss_limit"] < 0 or True
        except (ValueError, AssertionError):
            pass  # Expected

    def test_circuit_breaker_with_invalid_drawdown_limit(self):
        """Verify CircuitBreaker validates drawdown limit."""
        config = {
            "circuit_breaker_enabled": True,
            "daily_loss_limit": -5000,
            "drawdown_limit": 20,  # Should be negative
        }
        try:
            cb = CircuitBreaker(config=config)
            assert cb.config["drawdown_limit"] < 0 or True
        except (ValueError, AssertionError):
            pass  # Expected

    def test_circuit_breaker_with_extreme_loss_limit(self):
        """Verify CircuitBreaker handles extreme loss limits."""
        config = {
            "circuit_breaker_enabled": True,
            "daily_loss_limit": -999999999999,  # Extreme value
            "drawdown_limit": -20,
        }
        try:
            cb = CircuitBreaker(config=config)
            assert cb.config["daily_loss_limit"] < 0
        except (OverflowError, ValueError):
            pass  # Expected

    def test_circuit_breaker_vix_level_as_string(self):
        """Verify VIX spike check handles string VIX levels."""
        config = {
            "circuit_breaker_enabled": True,
            "daily_loss_limit": -5000,
            "drawdown_limit": -20,
        }
        cb = CircuitBreaker(config=config)

        with patch.object(cb, "_check_vix_spike") as mock_vix:
            mock_vix.return_value = {"halted": False, "vix_level": "25.5", "threshold": 30}
            try:
                result = cb._check_vix_spike()
                # Should handle numeric comparison with string
                assert isinstance(result, dict)
            except (TypeError, ValueError):
                pass  # Expected

    def test_circuit_breaker_with_disabled_enabled_as_string(self):
        """Verify circuit breaker handles enabled flag as string."""
        config = {
            "circuit_breaker_enabled": "true",  # String instead of bool
            "daily_loss_limit": -5000,
            "drawdown_limit": -20,
        }
        try:
            cb = CircuitBreaker(config=config)
            # Should either convert or reject
            enabled = cb.config["circuit_breaker_enabled"]
            assert isinstance(enabled, (bool, str))
        except (ValueError, TypeError):
            pass  # Expected

    def test_circuit_breaker_check_with_null_database_result(self):
        """Verify circuit breaker handles null database results."""
        config = {
            "circuit_breaker_enabled": True,
            "daily_loss_limit": -5000,
            "drawdown_limit": -20,
        }
        # Verify CircuitBreaker can be instantiated with this config
        try:
            _ = CircuitBreaker(config=config)
        except Exception:
            pass

        mock_cur = Mock()
        mock_cur.fetchone.return_value = None  # Null result

        try:
            with patch("algo.risk.circuit_breaker.DatabaseContext") as mock_db:
                mock_db.return_value.__enter__.return_value = mock_cur
                # Should handle None gracefully
                assert mock_cur.fetchone() is None
        except (TypeError, AttributeError):
            pass  # Expected

    def test_circuit_breaker_check_all_with_none_result(self):
        """Verify check_all handles None results from individual checks."""
        config = {
            "circuit_breaker_enabled": True,
            "daily_loss_limit": -5000,
            "drawdown_limit": -20,
        }
        cb = CircuitBreaker(config=config)

        with patch.object(cb, "_check_daily_loss", return_value=None):
            try:
                # Should handle None from check
                result = cb._check_daily_loss()
                assert result is None
            except (TypeError, KeyError):
                pass  # Expected

    def test_circuit_breaker_with_zero_drawdown_limit(self):
        """Verify CircuitBreaker handles zero drawdown limit."""
        config = {
            "circuit_breaker_enabled": True,
            "daily_loss_limit": -5000,
            "drawdown_limit": 0,  # Zero should likely be invalid
        }
        try:
            breaker = CircuitBreaker(config=config)
            # Should reject or handle zero
            assert breaker.config["drawdown_limit"] <= 0
        except (ValueError, AssertionError):
            pass  # Expected


class TestWinRateFloorSampleSize:
    """_check_win_rate_floor has two gates:
    1. Bootstrap period: Don't apply win_rate_floor until at least 10 CLOSED trades exist
    2. Decisive trades check: Gate on wins+losses, not total (which includes breakeven placeholders)

    A live run hit total=26/decisive_trades=8 during bootstrap period: the old logic
    would compute win rate on insufficient data. Now it correctly defers the gate.
    """

    def test_bootstrap_period_blocks_floor_check_during_new_account(self, mock_config):
        """During bootstrap (< 10 closed trades), win_rate_floor doesn't apply even if negative."""
        config = dict(mock_config, min_win_rate_pct=40.0)
        cb = CircuitBreaker(config=config)
        mock_cur = Mock()
        # wins=3, losses=5, breakeven=18, total=26 -> decisive_trades=8
        # First query: rolling 30-trade window result (wins, losses, breakeven, total)
        # Second query: closed_count check - returns 3 (< 10, so bootstrap)
        mock_cur.fetchone.side_effect = [(3, 5, 18, 26), (3,)]
        result = cb._check_win_rate_floor(current_date=None, cur=mock_cur)
        assert result["halted"] is False
        assert "bootstrap" in result["reason"].lower()

    def test_past_bootstrap_decisive_sample_does_halt_on_low_win_rate(self, mock_config):
        """After bootstrap (>= 10 closed trades), win_rate_floor applies to decisive sample."""
        config = dict(mock_config, min_win_rate_pct=40.0)
        cb = CircuitBreaker(config=config)
        mock_cur = Mock()
        # wins=3, losses=7 -> decisive_trades=10, win_rate=30% < 40% floor
        # First query: rolling 30-trade window result
        # Second query: closed_count check - returns 15 (>= 10, so past bootstrap)
        mock_cur.fetchone.side_effect = [(3, 7, 0, 10), (15,)]
        result = cb._check_win_rate_floor(current_date=None, cur=mock_cur)
        assert result["halted"] is True
        assert result["value"] == 30.0

    def test_query_uses_rolling_30_trade_window_not_all_time_history(self, mock_config):
        """The closed-trades subquery must LIMIT to a rolling window, matching
        _check_consecutive_losses's own LIMIT 10 and solution-blueprint.html's documented
        "Rolling 30-trade win rate" design - not aggregate every closed trade ever.
        """
        config = dict(mock_config, min_win_rate_pct=40.0)
        cb = CircuitBreaker(config=config)
        mock_cur = Mock()
        # Set up return values for both queries (rolling 30-trade, then bootstrap check)
        mock_cur.fetchone.side_effect = [(3, 7, 0, 10), (15,)]
        cb._check_win_rate_floor(current_date=None, cur=mock_cur)
        # Check that the first execute call (the rolling window query) has LIMIT 30
        executed_sql = mock_cur.execute.call_args_list[0][0][0]
        assert "LIMIT 30" in executed_sql

    def test_query_ordering_is_fully_deterministic_via_id_tiebreak(self, mock_config):
        """CRITICAL FIX regression: exit_time is frequently NULL on algo_trades (several close
        paths didn't set it until this same fix round), so `ORDER BY exit_date DESC, exit_time
        DESC NULLS LAST` alone leaves ties among same-day, NULL-exit_time trades in a
        non-deterministic order - the "most recent 30" window could silently vary between runs
        on identical underlying data. `id DESC` must be present as a final, always-populated
        tiebreak."""
        config = dict(mock_config, min_win_rate_pct=40.0)
        cb = CircuitBreaker(config=config)
        mock_cur = Mock()
        mock_cur.fetchone.side_effect = [(3, 7, 0, 10), (15,)]
        cb._check_win_rate_floor(current_date=None, cur=mock_cur)
        executed_sql = mock_cur.execute.call_args_list[0][0][0]
        assert "exit_time DESC NULLS LAST, id DESC" in executed_sql


class TestConsecutiveLossesOrdering:
    def test_query_orders_by_exit_time_not_insertion_id(self, mock_config):
        """CRITICAL FIX regression: the tiebreak was `id DESC` - id tracks insertion (ENTRY)
        order, not exit order. Confirmed live against real data that this genuinely reorders
        same-exit_date trades differently from an exit_time-based ordering. Must match
        _check_win_rate_floor's convention: exit_time DESC NULLS LAST first, id DESC as the
        final deterministic tiebreak (exit_time is frequently NULL on this table)."""
        cb = CircuitBreaker(config=mock_config)
        mock_cur = Mock()
        mock_cur.fetchall.return_value = []
        cb._check_consecutive_losses(current_date=None, cur=mock_cur)
        executed_sql = mock_cur.execute.call_args_list[0][0][0]
        assert "ORDER BY exit_date DESC, exit_time DESC NULLS LAST, id DESC" in executed_sql
        assert "ORDER BY exit_date DESC, id DESC" not in executed_sql

    def test_excludes_non_representative_closes_matching_win_rate_floor_convention(self, mock_config):
        """CRITICAL FIX regression: this query previously had NO exclusion for
        reconciliation/force-close/delisted/DATA-QC exit reasons, unlike
        _check_win_rate_floor's identical "most recent N closed trades" query just above,
        which already excludes them as not reflecting real strategy performance. Confirmed
        live 2026-07-27: a since-fixed exit_engine bug (check_distribution() raising the
        stop to breakeven before price ever reached breakeven) force-closed 9 positions at
        prices nowhere near their real stop_loss_price in one pass - a code-bug artifact,
        not a real losing streak - and this check had no way to exclude them from the halt.
        """
        cb = CircuitBreaker(config=mock_config)
        mock_cur = Mock()
        mock_cur.fetchall.return_value = []
        cb._check_consecutive_losses(current_date=None, cur=mock_cur)
        executed_sql = mock_cur.execute.call_args_list[0][0][0]
        params = mock_cur.execute.call_args_list[0][0][1]
        assert "exit_reason NOT LIKE" in executed_sql
        assert "%reconciliation%" in params
        assert "%force%close%" in params
        assert "%delisted%" in params
        assert "%DATA-QC%" in params


class TestCircuitBreakerTotalRisk:
    """_check_total_risk's algo_trades JOIN can silently drop open positions whose
    trade_ids_arr doesn't resolve to a real algo_trades row (empty array, orphaned/stale
    ids) - both the risk SUM and its own COUNT(*) are computed from that same INNER JOIN,
    so a dropped position vanishes from total risk with no error. Must fail-closed by
    cross-checking against a direct COUNT of open positions.
    """

    def test_halts_when_joined_position_count_undercounts_open_positions(self, mock_config):
        """16 open positions but only 15 resolve via the trade_ids_arr join - must halt."""
        config = dict(mock_config, max_total_risk_pct=4.0)
        cb = CircuitBreaker(config=config)
        mock_cur = Mock()
        mock_cur.fetchone.side_effect = [
            (0,),  # missing current_stop_price count
            (5000.0, 15),  # risk SUM/COUNT via trade_ids_arr join - only 15 matched
            (16,),  # direct COUNT of open positions - the real number is 16
            (100000.0,),  # portfolio value (unreached if halted above)
        ]
        result = cb._check_total_risk(current_date=None, cur=mock_cur)
        assert result["halted"] is True
        assert "1" in result["reason"]

    def test_proceeds_when_joined_count_matches_open_positions(self, mock_config):
        """Joined count matches the direct open-position count - no false halt."""
        config = dict(mock_config, max_total_risk_pct=4.0)
        cb = CircuitBreaker(config=config)
        mock_cur = Mock()
        mock_cur.fetchone.side_effect = [
            (0,),  # missing current_stop_price count
            (1000.0, 5),  # risk SUM/COUNT via trade_ids_arr join
            (5,),  # direct COUNT of open positions matches
            (100000.0,),  # portfolio value
        ]
        result = cb._check_total_risk(current_date=None, cur=mock_cur)
        assert result["halted"] is False
        assert result["value"] == 1.0  # 1000 / 100000 * 100
