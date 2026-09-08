"""Regression: a position missing at Alpaca (in DB but not at broker) re-alerted at the same
"warning" severity every reconciliation cycle forever, with no escalation - see the ORPHANED
BRACKET LEG FIX/CRITICAL FIX comments in alpaca_sync_manager.py's _sync_alpaca_positions_impl
for why auto-closing is deliberately NOT done (a prior incident caused mass false closures on
fill-pending/API lag). That reasoning only covers the DB-close decision - it never addressed
escalating operator attention as a genuine divergence persists.

Fixed 2026-09-07 (real-money-readiness audit): algo_positions.updated_at is the only signal
this branch ever writes for an open position (bumped only when the matched-position branch
finds it at Alpaca), so its staleness directly measures how long a position has actually been
missing, not just "missing this one check." A position still missing after
STALE_MISSING_ESCALATION_HOURS (24h - many reconciliation cycles) escalates to severity=critical
- the DB-side alert-only behavior (never auto-close) stays completely unchanged.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager


def _make_manager():
    manager = object.__new__(AlpacaSyncManager)
    manager.config = {"execution_mode": "auto", "api_request_timeout_seconds": 10}
    manager._alpaca_key = "key"
    manager._alpaca_secret = "secret"
    manager._alpaca_base_url = "https://paper-api.alpaca.markets"
    manager.fetch_alpaca_account = MagicMock()
    return manager


def _mock_response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


def _run_sync(missing_row_updated_at):
    manager = _make_manager()
    manager._session = MagicMock()
    manager._session.get.return_value = _mock_response([])  # Alpaca has nothing

    cur = MagicMock()
    cur.fetchall.side_effect = [
        [("STALEPOS", missing_row_updated_at)],  # missing_positions query
        [],  # db_symbols query
    ]
    cur.rowcount = 0

    mock_order_mgr = MagicMock()
    mock_order_mgr.cancel_all_open_orders_for_symbol.return_value = {
        "success": True,
        "cancelled_order_ids": [],
        "message": "no orders",
    }

    with (
        patch("algo.reporting.notify") as mock_notify,
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
    ):
        result = manager._sync_alpaca_positions_impl(cur)

    return result, mock_notify


def test_recently_missing_position_stays_warning_severity():
    result, mock_notify = _run_sync(datetime.now(timezone.utc) - timedelta(hours=1))
    assert result["closed_count"] == 0  # DB-close decision unaffected
    mock_notify.assert_called_once()
    assert mock_notify.call_args.kwargs["severity"] == "warning"


def test_persistently_missing_position_escalates_to_critical():
    result, mock_notify = _run_sync(datetime.now(timezone.utc) - timedelta(hours=25))
    assert result["closed_count"] == 0  # still never auto-closed
    mock_notify.assert_called_once()
    assert mock_notify.call_args.kwargs["severity"] == "critical"
    assert "STALEPOS" in mock_notify.call_args.kwargs["details"]["stale_missing"]


def test_naive_db_timestamp_normalized_via_db_session_timezone_not_assumed_utc():
    """algo_positions.updated_at is a naive `timestamp without time zone` column written via
    CURRENT_TIMESTAMP - a naive value is in the DB session's local timezone, not UTC (same
    convention as position_order_management.py's stale-order age check). America/Chicago is
    behind UTC by 5-6h, so mislabeling a Chicago wall-clock reading as if it were already UTC
    (without conversion) computes an INFLATED elapsed time (shifted earlier by the UTC offset,
    since Chicago's clock digits read lower than UTC's for the same instant) - a naive value
    correctly 20h old (should stay "warning", under the 24h threshold) would incorrectly read
    as ~25-26h old (wrongly escalating to "critical") if the DB-session-timezone conversion
    were skipped and UTC assumed instead.
    """
    from zoneinfo import ZoneInfo

    chicago = ZoneInfo("America/Chicago")
    # Correctly 20 hours old in real elapsed time - derived via aware Chicago arithmetic, then
    # stripped to a naive value the way the DB driver would actually return it.
    naive_local = (datetime.now(chicago) - timedelta(hours=20)).replace(tzinfo=None)

    with patch("utils.db.timezone_utils.get_db_timezone", return_value=chicago):
        result, mock_notify = _run_sync(naive_local)

    assert result["closed_count"] == 0
    # Correctly resolved via Chicago tz: 20h elapsed, under the 24h threshold - must NOT
    # escalate. (A UTC-mislabeling regression would inflate this to ~25-26h and wrongly flip
    # this assertion to "critical".)
    assert mock_notify.call_args.kwargs["severity"] == "warning"
