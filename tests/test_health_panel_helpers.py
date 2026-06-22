"""Unit tests for health panel helper functions."""

from datetime import datetime

from tools.dashboard.panels.health import (
    ERROR_STATES,
    HALTED_STATES,
    SUCCESS_STATES,
    _format_audit_log_summary,
    _format_daily_metrics_summary,
    _format_data_health_summary,
    _format_exec_history_summary,
    _format_loader_status,
    _format_notifications_summary,
    _format_phase_badge,
    _format_recent_trade_events,
)
from tools.dashboard.utilities import G, R, Y


class TestFormatPhaseBadge:
    """Test phase status badge formatting."""

    def test_success_status_returns_green_checkmark(self):
        color, icon = _format_phase_badge("success")
        assert color == G
        assert icon == "✓"

    def test_completed_status_returns_green_checkmark(self):
        color, icon = _format_phase_badge("completed")
        assert color == G
        assert icon == "✓"

    def test_ok_status_returns_green_checkmark(self):
        color, icon = _format_phase_badge("ok")
        assert color == G
        assert icon == "✓"

    def test_halted_status_returns_yellow_tilde(self):
        color, icon = _format_phase_badge("halted")
        assert color == Y
        assert icon == "~"

    def test_warn_status_returns_yellow_tilde(self):
        color, icon = _format_phase_badge("warn")
        assert color == Y
        assert icon == "~"

    def test_degraded_status_returns_yellow_tilde(self):
        color, icon = _format_phase_badge("degraded")
        assert color == Y
        assert icon == "~"

    def test_error_status_returns_red_x(self):
        color, icon = _format_phase_badge("error")
        assert color == R
        assert icon == "✗"

    def test_failed_status_returns_red_x(self):
        color, icon = _format_phase_badge("failed")
        assert color == R
        assert icon == "✗"

    def test_empty_status_returns_red_x(self):
        color, icon = _format_phase_badge("")
        assert color == R
        assert icon == "✗"

    def test_none_status_returns_red_x(self):
        color, icon = _format_phase_badge(None)
        assert color == R
        assert icon == "✗"

    def test_case_insensitive(self):
        color, icon = _format_phase_badge("SUCCESS")
        assert color == G
        assert icon == "✓"


class TestFormatExecHistorySummary:
    """Test execution history summary formatting."""

    def test_empty_history_returns_empty_list(self):
        result = _format_exec_history_summary([])
        assert result == []

    def test_none_history_returns_empty_list(self):
        result = _format_exec_history_summary(None)
        assert result == []

    def test_single_success_run(self):
        hist = [{"overall_status": "success"}]
        result = _format_exec_history_summary(hist)
        assert len(result) > 0
        # Should contain success indicator
        result_str = str(result[0])
        assert "1/1 success" in result_str or "success" in result_str

    def test_mixed_results(self):
        hist = [
            {"overall_status": "success"},
            {"overall_status": "success"},
            {"overall_status": "halted"},
            {"overall_status": "error"},
        ]
        result = _format_exec_history_summary(hist)
        assert len(result) > 0

    def test_last_halt_shown_in_details(self):
        hist = [
            {"overall_status": "success"},
            {"overall_status": "halted", "halt_reason": "Market closed", "phases_halted": []},
        ]
        result = _format_exec_history_summary(hist)
        # Should have details about halt if available
        assert len(result) >= 1


class TestFormatDataHealthSummary:
    """Test data health summary formatting."""

    def test_empty_health_items_returns_empty_list(self):
        result = _format_data_health_summary([])
        assert result == []

    def test_all_healthy_tables(self):
        items = [
            {"st": "ok", "tbl": "trades", "role": "CRIT"},
            {"st": "ok", "tbl": "positions", "role": "IMP"},
        ]
        result = _format_data_health_summary(items)
        assert len(result) > 0
        result_str = str(result[0])
        assert "ok" in result_str.lower() or "OK" in result_str

    def test_stale_tables_shown(self):
        items = [
            {"st": "stale", "tbl": "prices", "role": "CRIT", "age_hours": 48},
            {"st": "ok", "tbl": "trades", "role": "IMP"},
        ]
        result = _format_data_health_summary(items)
        assert len(result) > 0
        # Stale table should be listed
        result_str = " ".join(str(r) for r in result)
        assert "stale" in result_str.lower() or "prices" in result_str

    def test_critical_stale_highlighted(self):
        items = [
            {"st": "stale", "tbl": "market_data", "role": "CRIT", "age_hours": 24},
        ]
        result = _format_data_health_summary(items)
        assert len(result) > 0


class TestFormatNotificationsSummary:
    """Test notifications summary formatting."""

    def test_empty_notifications_returns_empty_list(self):
        result = _format_notifications_summary([])
        assert result == []

    def test_single_critical_notification(self):
        notifs = [
            {
                "severity": "critical",
                "title": "Trading halted by circuit breaker",
                "created_at": datetime.now(),
                "seen": True,
            }
        ]
        result = _format_notifications_summary(notifs)
        assert len(result) > 0
        result_str = str(result[0])
        # Should contain either full title or short name
        assert "halted" in result_str.lower() or "circuit" in result_str.lower()

    def test_notification_age_formatting(self):
        now = datetime.now()
        notifs = [{"severity": "warning", "title": "Position exited", "created_at": now, "seen": False}]
        result = _format_notifications_summary(notifs)
        assert len(result) > 0

    def test_unread_indicator_shown(self):
        notifs = [{"severity": "info", "title": "New signal", "created_at": datetime.now(), "seen": False}]
        result = _format_notifications_summary(notifs)
        assert len(result) > 0
        # Unread should show as "-" or indicator
        result_str = str(result[0])
        assert "-" in result_str  # Unread indicator


class TestFormatLoaderStatus:
    """Test data loader status formatting."""

    def test_empty_loader_returns_empty_list(self):
        result = _format_loader_status([])
        assert result == []

    def test_healthy_loaders_shown(self):
        loader = [
            {"status": "ok", "table_name": "prices", "completion_pct": 100},
            {"status": "ok", "table_name": "trades", "completion_pct": 100},
        ]
        result = _format_loader_status(loader)
        assert len(result) > 0
        result_str = " ".join(str(r) for r in result)
        assert "healthy" in result_str.lower() or "ok" in result_str.lower()

    def test_problem_loaders_shown(self):
        loader = [
            {"status": "error", "table_name": "options", "age_days": 5, "error_message": "API timeout"},
            {"status": "ok", "table_name": "trades", "completion_pct": 100},
        ]
        result = _format_loader_status(loader)
        assert len(result) > 0
        result_str = " ".join(str(r) for r in result)
        assert "error" in result_str.lower() or "issue" in result_str.lower()

    def test_loading_loaders_shown(self):
        loader = [
            {"status": "loading", "table_name": "signals", "completion_pct": 45},
        ]
        result = _format_loader_status(loader)
        assert len(result) > 0
        result_str = " ".join(str(r) for r in result)
        assert "load" in result_str.lower() or "45" in result_str


class TestFormatDailyMetricsSummary:
    """Test daily metrics summary formatting."""

    def test_empty_metrics_returns_empty_list(self):
        result = _format_daily_metrics_summary([])
        assert result == []

    def test_single_day_metrics(self):
        metrics = [
            {
                "date": datetime(2026, 6, 20),
                "total_actions": 5,
                "entries": 3,
                "exits": 2,
            }
        ]
        result = _format_daily_metrics_summary(metrics)
        assert len(result) > 0
        result_str = " ".join(str(r) for r in result)
        assert "activity" in result_str.lower() or "3" in result_str or "5" in result_str

    def test_multiple_days_metrics(self):
        metrics = [
            {"date": datetime(2026, 6, 20), "total_actions": 5, "entries": 3, "exits": 2},
            {"date": datetime(2026, 6, 19), "total_actions": 4, "entries": 2, "exits": 2},
        ]
        result = _format_daily_metrics_summary(metrics)
        assert len(result) > 0


class TestFormatRecentTradeEvents:
    """Test recent trade events formatting."""

    def test_empty_activity_returns_empty_list(self):
        result = _format_recent_trade_events({})
        assert result == []

    def test_no_recent_actions(self):
        act = {"recent_actions": []}
        result = _format_recent_trade_events(act)
        assert result == []

    def test_trade_event_formatted(self):
        act = {
            "recent_actions": [
                {
                    "action_type": "entry_executed",
                    "details": '{"symbol": "AAPL"}',
                }
            ]
        }
        result = _format_recent_trade_events(act)
        assert len(result) > 0
        result_str = str(result[0])
        assert "entry" in result_str.lower() or "AAPL" in result_str

    def test_exit_event_formatted(self):
        act = {
            "recent_actions": [
                {
                    "action_type": "exit_executed",
                    "details": '{"symbol": "TSLA"}',
                }
            ]
        }
        result = _format_recent_trade_events(act)
        assert len(result) > 0


class TestFormatAuditLogSummary:
    """Test audit log summary formatting."""

    def test_empty_audit_returns_empty_list(self):
        result = _format_audit_log_summary([])
        assert result == []

    def test_notable_actions_filtered(self):
        audit = [
            {"action_type": "entry_executed", "symbol": "SPY", "status": "success"},
            {"action_type": "check_signal", "status": "success"},  # Not notable
        ]
        result = _format_audit_log_summary(audit)
        assert len(result) > 0
        result_str = " ".join(str(r) for r in result)
        assert "entry" in result_str.lower()

    def test_halt_action_shown(self):
        audit = [
            {"action_type": "trading_halted", "status": "success"},
        ]
        result = _format_audit_log_summary(audit)
        assert len(result) > 0


# Test constants
class TestConstants:
    """Test that constants are properly defined."""

    def test_success_states_defined(self):
        assert "success" in SUCCESS_STATES
        assert "completed" in SUCCESS_STATES
        assert "ok" in SUCCESS_STATES

    def test_halted_states_defined(self):
        assert "halt" in HALTED_STATES
        assert "halted" in HALTED_STATES
        assert "warn" in HALTED_STATES

    def test_error_states_defined(self):
        assert "error" in ERROR_STATES
        assert "failed" in ERROR_STATES
