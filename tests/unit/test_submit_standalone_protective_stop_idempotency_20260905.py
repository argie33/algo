"""Regression test: submit_standalone_protective_stop must not place a duplicate live
protective stop when an earlier call's outcome is ambiguous or its DB write was lost.

BUG FOUND 2026-09-05 (real-money-readiness audit, ported from an unmerged WIP fix found
while checking on flagged gaps): submit_standalone_protective_stop accepted a
client_order_id param but the only caller (phase9_stop_loss_repair.py) never passed one,
and no ground-truth lookup existed on an ambiguous timeout/network-exception/422 outcome -
unlike the entry/exit order paths, which already use exactly this pattern (client_order_id
+ _lookup_order_by_client_order_id) to tell "genuinely failed" apart from "succeeded but
the response was lost, this is a crash-recovery retry". A lost response in this repair
path could previously either falsely report failure for a stop that actually went live,
or place a second live protective stop for the same shares.

Two layers close this: (1) a broker-side preflight check (_find_open_sell_stop_order)
that catches an EARLIER cycle's repair whose broker call succeeded but whose DB write
(standalone_stop_order_id) never landed, and (2) the same client_order_id ground-truth
lookup on an ambiguous outcome within a single call's own retry loop that entry/exit
orders already use.
"""

from unittest.mock import MagicMock, patch

import requests

from algo.trading.order_manager import OrderManager


def _make_manager() -> OrderManager:
    return OrderManager(alpaca_key="key", alpaca_secret="secret", alpaca_base_url="https://api.example.com")


class TestPreflightReusesExistingRestingStop:
    def test_existing_open_sell_stop_order_is_reused_not_duplicated(self):
        """An earlier repair's broker call succeeded but its DB write never landed - the
        next cycle's repair attempt must find and reuse that resting order, not submit a
        second live stop for the same shares."""
        manager = _make_manager()
        existing_order = {"id": "existing-order-1", "side": "sell", "type": "stop"}

        with (
            patch.object(manager, "_find_open_sell_stop_order", return_value=existing_order),
            patch("algo.trading.order_manager_stop_repair.requests.post") as mock_post,
        ):
            result = manager.submit_standalone_protective_stop("AAPL", 10.0, 150.0)

        assert result["success"] is True
        assert result["order_id"] == "existing-order-1"
        mock_post.assert_not_called()

    def test_preflight_check_failure_skips_submission_rather_than_risking_a_duplicate(self):
        """REAL-MONEY-READINESS FIX (2026-09-06 audit): if the preflight check itself errors
        (e.g. transient API failure), a failed-open fall-through to normal submission always
        generates a FRESH client_order_id (no client_order_id is passed by the only real
        caller), so the client_order_id ground-truth lookup below can never catch a genuine
        duplicate either - it only matches a retry of the SAME id. That left duplicate-order
        prevention resting entirely on Alpaca's own 422 qty-reservation rejection, in exactly
        the failure mode (broker API instability) where that backstop is least trustworthy.
        Skip this repair cycle instead - the position stays protected by whatever stop
        already exists, and the next cycle retries once the broker is reachable again."""
        manager = _make_manager()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "new-order-1"}

        with (
            patch.object(manager, "_find_open_sell_stop_order", side_effect=RuntimeError("API down")),
            patch("algo.trading.order_manager_stop_repair.requests.post", return_value=mock_resp) as mock_post,
        ):
            result = manager.submit_standalone_protective_stop("AAPL", 10.0, 150.0)

        assert result["success"] is False
        mock_post.assert_not_called()


class TestClientOrderIdGroundTruthRecovery:
    def test_timeout_recovers_via_client_order_id_lookup(self):
        """A network timeout during submission is ambiguous - the order may have gone live
        with the response lost. Must look up by client_order_id and report the EXISTING
        order rather than treating this as an outright failure (which could otherwise
        prompt a caller to retry with a fresh client_order_id and truly double-submit)."""
        manager = _make_manager()

        with (
            patch.object(manager, "_find_open_sell_stop_order", return_value=None),
            patch(
                "algo.trading.order_manager_stop_repair.requests.post",
                side_effect=requests.Timeout("timed out"),
            ),
            patch.object(
                manager,
                "_lookup_order_by_client_order_id",
                return_value={"id": "recovered-order-1"},
            ) as mock_lookup,
            patch("algo.trading.order_manager_stop_repair.time.sleep"),
        ):
            result = manager.submit_standalone_protective_stop(
                "AAPL", 10.0, 150.0, client_order_id="stoprepair-1-abc123"
            )

        assert result["success"] is True
        assert result["order_id"] == "recovered-order-1"
        mock_lookup.assert_called_with("stoprepair-1-abc123")

    def test_no_client_order_id_means_no_recovery_possible(self):
        """Without a client_order_id, there is nothing to look up - an ambiguous failure
        must report failure rather than fabricate a recovery."""
        manager = _make_manager()

        with (
            patch.object(manager, "_find_open_sell_stop_order", return_value=None),
            patch(
                "algo.trading.order_manager_stop_repair.requests.post",
                side_effect=requests.Timeout("timed out"),
            ),
            patch("algo.trading.order_manager_stop_repair.time.sleep"),
        ):
            result = manager.submit_standalone_protective_stop("AAPL", 10.0, 150.0)

        assert result["success"] is False
