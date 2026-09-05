"""Regression test for OrderManager.get_order / replace_order_stop_price /
sync_bracket_stop_loss - the 2026-08-24 fix that closes the "trailed stop never
reaches the broker" gap.

send_bracket_order() submits a real Alpaca bracket order at entry with a live
stop-loss leg - real broker-side protection, independent of our own polling. But
until this fix, nothing ever updated that leg's price when our own logic later
decided to raise the stop (breakeven move, chandelier trail, position_monitor's
trailing recommendation): the resting order stayed at its original, wider price
forever. sync_bracket_stop_loss() closes that by fetching the parent order's current
`legs`, finding the live stop-loss leg, and PATCHing its stop_price.
"""

from unittest.mock import MagicMock, patch

from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


class TestGetOrder:
    def test_paper_local_order_returns_none_without_http_call(self):
        manager = _make_manager()
        with patch("algo.trading.order_manager.requests.get") as mock_get:
            result = manager.get_order("LOCAL-abc123")
        assert result is None
        mock_get.assert_not_called()

    def test_200_returns_parsed_order(self):
        manager = _make_manager()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"id": "parent-1", "legs": [{"id": "leg-1", "order_type": "stop"}]}
        with patch("algo.trading.order_manager.requests.get", return_value=resp):
            result = manager.get_order("parent-1")
        assert result["legs"][0]["id"] == "leg-1"

    def test_429_then_success_retries(self):
        manager = _make_manager()
        rate_limited = MagicMock(status_code=429, text="rate limited")
        ok = MagicMock(status_code=200)
        ok.json.return_value = {"id": "parent-1", "legs": []}
        with (
            patch("algo.trading.order_manager.requests.get", side_effect=[rate_limited, ok]),
            patch("algo.trading.order_manager.time.sleep"),
        ):
            result = manager.get_order("parent-1")
        assert result["id"] == "parent-1"


class TestReplaceOrderStopPrice:
    def test_success_returns_new_order_id(self):
        manager = _make_manager()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"id": "leg-2-replacement"}
        with patch("algo.trading.order_manager.requests.patch", return_value=resp):
            result = manager.replace_order_stop_price("leg-1", 105.0)
        assert result["success"] is True
        assert result["new_order_id"] == "leg-2-replacement"

    def test_transient_failure_retries_then_succeeds(self):
        manager = _make_manager()
        unavailable = MagicMock(status_code=503, text="unavailable")
        ok = MagicMock(status_code=200)
        ok.json.return_value = {"id": "leg-2"}
        with (
            patch("algo.trading.order_manager.requests.patch", side_effect=[unavailable, ok]),
            patch("algo.trading.order_manager.time.sleep"),
        ):
            result = manager.replace_order_stop_price("leg-1", 105.0)
        assert result["success"] is True

    def test_permanent_failure_does_not_raise_returns_failure_dict(self):
        """Unlike cancel_bracket_orders (best-effort cleanup that raises), a replace
        failure must be reported back to the caller as a normal dict so
        ExitHandler._raise_stop can fail the stop-raise closed without crashing the
        whole exit-processing loop for one symbol."""
        manager = _make_manager()
        rejected = MagicMock(status_code=422, text="order not replaceable")
        with patch("algo.trading.order_manager.requests.patch", return_value=rejected):
            result = manager.replace_order_stop_price("leg-1", 105.0)
        assert result["success"] is False
        assert "422" in result["message"]


class TestSyncBracketStopLoss:
    def test_no_alpaca_order_id_is_success_not_synced(self):
        manager = _make_manager()
        result = manager.sync_bracket_stop_loss(None, 105.0)
        assert result == {
            "success": True,
            "synced": False,
            "message": "No live Alpaca order to sync (paper/local mode)",
        }

    def test_local_order_id_is_success_not_synced(self):
        manager = _make_manager()
        with patch("algo.trading.order_manager.requests.get") as mock_get:
            result = manager.sync_bracket_stop_loss("LOCAL-abc", 105.0)
        assert result["success"] is True
        assert result["synced"] is False
        mock_get.assert_not_called()

    def test_finds_live_stop_leg_and_replaces_it(self):
        manager = _make_manager()
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = {
            "id": "parent-1",
            "legs": [
                {"id": "tp-leg", "order_type": "limit", "status": "new"},
                {"id": "stop-leg", "order_type": "stop", "status": "new"},
            ],
        }
        patch_resp = MagicMock(status_code=200)
        patch_resp.json.return_value = {"id": "stop-leg-replacement"}

        with (
            patch("algo.trading.order_manager.requests.get", return_value=get_resp),
            patch("algo.trading.order_manager.requests.patch", return_value=patch_resp) as mock_patch,
        ):
            result = manager.sync_bracket_stop_loss("parent-1", 105.0)

        assert result["success"] is True
        assert mock_patch.call_args[0][0].endswith("/v2/orders/stop-leg")

    def test_ignores_filled_or_canceled_stop_leg(self):
        """A stop leg with a terminal status isn't live - e.g. the position already
        closed via broker fill moments before this ran. Must not try to replace it."""
        manager = _make_manager()
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = {
            "id": "parent-1",
            "legs": [{"id": "stop-leg", "order_type": "stop", "status": "filled"}],
        }
        with (
            patch("algo.trading.order_manager.requests.get", return_value=get_resp),
            patch("algo.trading.order_manager.requests.patch") as mock_patch,
        ):
            result = manager.sync_bracket_stop_loss("parent-1", 105.0)

        assert result["success"] is False
        assert "No live stop-loss leg" in result["message"]
        mock_patch.assert_not_called()

    def test_never_caches_leg_id_across_calls_refetches_each_time(self):
        """Alpaca replace is cancel-and-recreate: the leg id changes on every replace.
        sync_bracket_stop_loss must re-fetch the parent order fresh each call, not reuse
        a previously-returned new_order_id."""
        manager = _make_manager()

        first_get = MagicMock(status_code=200)
        first_get.json.return_value = {
            "id": "parent-1",
            "legs": [{"id": "stop-leg-v1", "order_type": "stop", "status": "new"}],
        }
        first_patch = MagicMock(status_code=200)
        first_patch.json.return_value = {"id": "stop-leg-v2"}

        second_get = MagicMock(status_code=200)
        second_get.json.return_value = {
            "id": "parent-1",
            "legs": [{"id": "stop-leg-v2", "order_type": "stop", "status": "new"}],
        }
        second_patch = MagicMock(status_code=200)
        second_patch.json.return_value = {"id": "stop-leg-v3"}

        with (
            patch("algo.trading.order_manager.requests.get", side_effect=[first_get, second_get]),
            patch("algo.trading.order_manager.requests.patch", side_effect=[first_patch, second_patch]) as mock_patch,
        ):
            manager.sync_bracket_stop_loss("parent-1", 105.0)
            manager.sync_bracket_stop_loss("parent-1", 110.0)

        assert mock_patch.call_args_list[0][0][0].endswith("/v2/orders/stop-leg-v1")
        assert mock_patch.call_args_list[1][0][0].endswith("/v2/orders/stop-leg-v2")


class TestCheckStopLossLegLive:
    """check_stop_loss_leg_live is the READ-ONLY counterpart to sync_bracket_stop_loss,
    added 2026-09-04 for phase9_reconciliation.py's proactive stop-loss protection check
    (real-money-readiness finding: day-TIF bracket legs might not survive past the entry
    day, and nothing previously re-verified protection on a flat/non-trailing position).
    It must NEVER call requests.patch - a periodic "are we still protected" check that
    itself triggers a cancel-and-recreate replace would defeat its own purpose."""

    def test_no_alpaca_order_id_is_unchecked_not_unprotected(self):
        manager = _make_manager()
        with patch("algo.trading.order_manager.requests.get") as mock_get:
            result = manager.check_stop_loss_leg_live(None)
        assert result == {
            "checked": False,
            "has_live_stop_loss": None,
            "message": "No live Alpaca order to check (paper/local mode)",
        }
        mock_get.assert_not_called()

    def test_local_order_id_is_unchecked_not_unprotected(self):
        manager = _make_manager()
        with patch("algo.trading.order_manager.requests.get") as mock_get:
            result = manager.check_stop_loss_leg_live("LOCAL-abc")
        assert result["checked"] is False
        assert result["has_live_stop_loss"] is None
        mock_get.assert_not_called()

    def test_live_stop_leg_present_reports_protected(self):
        manager = _make_manager()
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = {
            "id": "parent-1",
            "legs": [
                {"id": "tp-leg", "order_type": "limit", "status": "new"},
                {"id": "stop-leg", "order_type": "stop", "status": "new"},
            ],
        }
        with (
            patch("algo.trading.order_manager.requests.get", return_value=get_resp),
            patch("algo.trading.order_manager.requests.patch") as mock_patch,
        ):
            result = manager.check_stop_loss_leg_live("parent-1")

        assert result == {"checked": True, "has_live_stop_loss": True, "message": "stop-loss leg live"}
        mock_patch.assert_not_called()

    def test_missing_stop_leg_reports_unprotected(self):
        """The core case this check exists for: the stop-loss leg is gone (whatever the
        reason - expired day-TIF, manual cancel, broker glitch) while the position is
        still open. Must be flagged, not silently treated as fine."""
        manager = _make_manager()
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = {
            "id": "parent-1",
            "legs": [{"id": "tp-leg", "order_type": "limit", "status": "new"}],
        }
        with (
            patch("algo.trading.order_manager.requests.get", return_value=get_resp),
            patch("algo.trading.order_manager.requests.patch") as mock_patch,
        ):
            result = manager.check_stop_loss_leg_live("parent-1")

        assert result["checked"] is True
        assert result["has_live_stop_loss"] is False
        assert "No live stop-loss leg" in result["message"]
        mock_patch.assert_not_called()

    def test_terminal_status_stop_leg_reports_unprotected(self):
        """A stop leg with status='canceled'/'expired'/'filled' is not live protection -
        exactly the day-TIF-expiry scenario this check is meant to catch."""
        manager = _make_manager()
        for terminal_status in ("canceled", "expired", "filled", "rejected", "replaced"):
            get_resp = MagicMock(status_code=200)
            get_resp.json.return_value = {
                "id": "parent-1",
                "legs": [{"id": "stop-leg", "order_type": "stop", "status": terminal_status}],
            }
            with patch("algo.trading.order_manager.requests.get", return_value=get_resp):
                result = manager.check_stop_loss_leg_live("parent-1")
            assert result["has_live_stop_loss"] is False, f"status={terminal_status} should not count as live"

    def test_agrees_with_sync_bracket_stop_loss_on_same_legs(self):
        """Both methods share _find_live_stop_loss_leg - assert they never disagree on
        the same order data, since that's the whole point of factoring it out."""
        manager = _make_manager()
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = {
            "id": "parent-1",
            "legs": [{"id": "stop-leg", "order_type": "stop", "status": "held"}],
        }
        patch_resp = MagicMock(status_code=200)
        patch_resp.json.return_value = {"id": "stop-leg-replacement"}

        with patch("algo.trading.order_manager.requests.get", return_value=get_resp):
            check_result = manager.check_stop_loss_leg_live("parent-1")
        with (
            patch("algo.trading.order_manager.requests.get", return_value=get_resp),
            patch("algo.trading.order_manager.requests.patch", return_value=patch_resp),
        ):
            sync_result = manager.sync_bracket_stop_loss("parent-1", 105.0)

        assert check_result["has_live_stop_loss"] is True
        assert sync_result["success"] is True
