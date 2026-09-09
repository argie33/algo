"""Regression test for a 2026-09-07 pre-live-trading audit fix to
position_corporate_actions.py's _fetch_alpaca_position()/check_corporate_actions().

BUG FOUND: Alpaca returns 404 (not qty=0) for a position that no longer exists at the broker -
a symbol that closed, was delisted, or was renamed by a merger/ticker change. _fetch_alpaca_position
used to raise RuntimeError for ANY non-200 status including 404, and check_corporate_actions's
per-symbol try/except only caught psycopg2 errors - so that RuntimeError propagated out of the
whole loop uncaught, silently aborting corporate-action detection (including split-adjustment)
for every OTHER open position in the same cycle. One delisted symbol could leave a genuine stock
split on a completely different, healthy position unadjusted.

Fix: 404 is treated as "no position at broker" (returns None, handled identically to a real
qty=0 - matching the established 200/204/404 pattern already used elsewhere for this exact
endpoint), and any other unexpected per-symbol RuntimeError is caught and logged without
aborting the batch.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from algo.monitoring.position_monitor import PositionMonitor


def _mock_response(status_code: int, json_body: dict[str, Any] | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    return resp


class TestCorporateActions404DoesNotAbortBatch:
    def test_404_for_one_symbol_still_processes_remaining_positions(self) -> None:
        """DELISTED (404 - no position at broker) must not prevent HEALTHY's real split from
        being detected and adjusted in the same cycle."""
        monitor = PositionMonitor(config={"api_request_timeout_seconds": 10})
        cur = MagicMock()
        cur.fetchall.return_value = [
            (1, "DELISTED", 50, 45.00, 50.00, ["TRD-1"]),
            (2, "HEALTHY", 50, 45.00, 50.00, ["TRD-2"]),
        ]

        responses = {
            "DELISTED": _mock_response(404),
            "HEALTHY": _mock_response(200, {"qty": "100"}),  # 2:1 split
        }

        def _fake_get(url: str, headers: Any = None, timeout: Any = None) -> MagicMock:
            for sym, resp in responses.items():
                if sym in url:
                    return resp
            raise AssertionError(f"unexpected URL: {url}")

        with (
            patch("algo.monitoring.position_monitor.DatabaseContext") as MockCtx,
            patch.object(monitor, "_get_alpaca_creds", return_value=("https://api/v2/positions", "key", "secret")),
            patch("algo.monitoring.position_corporate_actions._pm.requests.get", side_effect=_fake_get),
        ):
            MockCtx.return_value.__enter__.return_value = cur
            adjustments = monitor.check_corporate_actions()

        symbols_adjusted = {a["symbol"] for a in adjustments}
        assert "DELISTED" in symbols_adjusted, "404 must still be recorded as closed-at-broker"
        assert "HEALTHY" in symbols_adjusted, (
            "DELISTED's 404 must not prevent HEALTHY's real split from being processed in the same cycle"
        )
        delisted_adjustment = next(a for a in adjustments if a["symbol"] == "DELISTED")
        assert delisted_adjustment["action"] == "POSITION_CLOSED_AT_ALPACA"
        assert delisted_adjustment["alpaca_qty"] is None
