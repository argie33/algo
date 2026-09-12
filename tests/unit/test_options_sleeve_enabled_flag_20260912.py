"""Regression test: the options CSP/covered-call sleeve (screener API + dashboard fetcher)
is disabled by default and only activates via OPTIONS_SLEEVE_ENABLED=true.

Covers the flag added 2026-09-12 alongside completing the options-sleeve branch merge -
CLAUDE.md documents the same behavior. Deliberately does NOT test
algo/orchestrator/phase8_guards.py's check_options_sleeve_overlap - that capital-safety
guard is unaffected by this flag and stays always-on (see test_phase8_entry_options_sleeve_overlap_gate_20260912.py).

'lambda' is a Python keyword, so lambda/api modules are loaded via importlib with lambda/api
on sys.path, matching this repo's existing convention (see
test_route_auth_guard_matches_canonical_check_admin_access.py).

Verified via: python -m pytest tests/unit/test_options_sleeve_enabled_flag_20260912.py -v
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

_api_dir = str(Path(__file__).resolve().parents[2] / "lambda" / "api")
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

options_route = importlib.import_module("routes.options")

from dashboard.fetchers_options import fetch_options


def test_route_disabled_by_default() -> None:
    with patch.dict("os.environ", {}, clear=False):
        import os as _os

        _os.environ.pop("OPTIONS_SLEEVE_ENABLED", None)
        result = options_route.handle(cur=None, path="/api/options", method="GET", params={})
    assert result["statusCode"] == 404
    assert result["errorType"] == "feature_disabled"


def test_route_disabled_when_flag_explicitly_false() -> None:
    with patch.dict("os.environ", {"OPTIONS_SLEEVE_ENABLED": "false"}):
        result = options_route.handle(cur=None, path="/api/options", method="GET", params={})
    assert result["statusCode"] == 404


def test_route_does_not_touch_db_when_disabled() -> None:
    """A disabled request must short-circuit before ever using the cursor."""
    with patch.dict("os.environ", {"OPTIONS_SLEEVE_ENABLED": "false"}):
        # cur=None would raise/attribute-error if handle() tried to use it - passing None
        # instead of a mock cursor IS the assertion here.
        result = options_route.handle(cur=None, path="/api/options", method="GET", params={})
    assert result["statusCode"] == 404


def test_fetcher_disabled_by_default_does_not_call_api() -> None:
    with patch.dict("os.environ", {}, clear=False):
        import os as _os

        _os.environ.pop("OPTIONS_SLEEVE_ENABLED", None)
        with patch("dashboard.fetchers_options.api_call") as mock_api_call:
            result = fetch_options(None)
    mock_api_call.assert_not_called()
    assert "_error" in result
    assert "OPTIONS_SLEEVE_ENABLED" in result["_error"]


def test_fetcher_disabled_does_not_record_data_quality_issue() -> None:
    with patch.dict("os.environ", {"OPTIONS_SLEEVE_ENABLED": "false"}):
        with patch("dashboard.fetchers_options.record_data_quality_issue") as mock_record:
            fetch_options(None)
    mock_record.assert_not_called()
