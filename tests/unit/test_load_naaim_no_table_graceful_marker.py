"""Regression test for the 2026-08-11 fix: NAAIMExposureLoader.fetch_global() crashed with an
unhandled RuntimeError whenever NAAIM's public page had zero <table> elements, instead of
returning the explicit data_unavailable marker the code already had a branch for.

Root cause: pandas.read_html() raises ValueError("No tables found matching regex '.+'") when
it finds no tables - it never returns an empty list - so the pre-existing `if not tables:`
graceful-fallback check could never actually be reached. Live-confirmed real-world trigger:
NAAIM's page banner states the Exposure Index transitioned to a subscription-based access
model on 2026-08-01, so the free public page genuinely has no data table anymore (not a
transient site glitch) - this crashed the loader on every single run for 13+ days.
"""

from unittest.mock import MagicMock, patch

from loaders.load_naaim import NAAIMExposureLoader


class TestNaaimNoTableGracefulMarker:
    def test_fetch_global_returns_data_unavailable_marker_when_read_html_raises(self) -> None:
        loader = NAAIMExposureLoader()
        mock_response = MagicMock(status_code=200, text="<html><body>No table here</body></html>")
        mock_response.raise_for_status = MagicMock()

        with (
            patch("loaders.load_naaim.validate_url", return_value=(True, None)),
            patch("loaders.load_naaim.requests.get", return_value=mock_response),
            patch(
                "loaders.load_naaim.pd.read_html",
                side_effect=ValueError("No tables found matching regex '.+'"),
            ),
        ):
            result = loader.fetch_global(since=None)

        assert result == [{"data_unavailable": True, "reason": "no_data_tables_found"}]
