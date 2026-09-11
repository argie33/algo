"""Unit test (2026-09-11, goal: "resources we should be tapping into" ask) for
scripts/xbrl_dera_bulk_scan.py's quarter-arithmetic helpers - the part of that script most
likely to silently misbehave (a wrong quarter means "not found" for a real filer, easily
misread as "this filer genuinely lacks the concept").
"""

import urllib.error
from unittest.mock import patch

from scripts.xbrl_dera_bulk_scan import _next_quarter, _quarter_for_date, download_quarter


class TestQuarterForDate:
    def test_maps_month_to_correct_quarter(self):
        assert _quarter_for_date("2025-10-31") == "2025q4"
        assert _quarter_for_date("2026-03-25") == "2026q1"
        assert _quarter_for_date("2026-01-09") == "2026q1"
        assert _quarter_for_date("2026-06-30") == "2026q2"
        assert _quarter_for_date("2026-09-11") == "2026q3"


class TestNextQuarter:
    def test_rolls_within_year(self):
        assert _next_quarter("2026q1") == "2026q2"
        assert _next_quarter("2026q3") == "2026q4"

    def test_rolls_over_year_boundary(self):
        assert _next_quarter("2026q4") == "2027q1"


class TestDownloadQuarterNotYetPublished:
    def test_returns_none_on_404_instead_of_raising(self, tmp_path):
        with (
            patch("scripts.xbrl_dera_bulk_scan._DERA_CACHE_DIR", tmp_path),
            patch(
                "scripts.xbrl_dera_bulk_scan.urllib.request.urlopen",
                side_effect=urllib.error.HTTPError("url", 404, "Not Found", {}, None),
            ),
        ):
            assert download_quarter("2099q1") is None

    def test_reraises_non_404_http_errors(self, tmp_path):
        with (
            patch("scripts.xbrl_dera_bulk_scan._DERA_CACHE_DIR", tmp_path),
            patch(
                "scripts.xbrl_dera_bulk_scan.urllib.request.urlopen",
                side_effect=urllib.error.HTTPError("url", 500, "Server Error", {}, None),
            ),
        ):
            try:
                download_quarter("2026q3")
            except urllib.error.HTTPError as e:
                assert e.code == 500
            else:
                raise AssertionError("expected HTTPError to propagate")
