"""Regression test for the LOADER_PARALLELISM=2 override for SEC-only loaders.

local_loader_scheduler.py force-defaults LOADER_PARALLELISM=1 for every loader (to protect
yfinance from a self-triggered shared-IP ban, see the module-level comment above
_LOADER_PARALLELISM_AUTO_DEFAULTED). That blanket default also silently halved the
designed-safe parallelism (up to 2, per utils/loaders/config.py's LOADER_CONSTRAINTS) of
company_info_sec/earnings_calendar_sec, which are pure-SEC loaders with nothing to do with
yfinance. Fixed (goal session 20260908) by overriding LOADER_PARALLELISM=2 specifically for
those loaders' child env - but only when this script chose the "1" default itself, never
when an operator explicitly set LOADER_PARALLELISM before running it. financial_statements
is deliberately excluded: its LOADER_STATEMENT_TYPE=all mode ignores --parallelism entirely
(serial symbol-major pass, one companyfacts fetch covers all 6 combos per symbol), so an
override there would be a silent no-op.
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.test_local_loader_scheduler_direct_invocation import _load_scheduler_module, _mock_proc


@pytest.mark.parametrize("shorthand", ["company_info", "earnings_sec"])
def test_sec_only_loaders_get_parallelism_2_when_auto_defaulted(shorthand, tmp_path, monkeypatch):
    monkeypatch.delenv("LOADER_PARALLELISM", raising=False)
    module = _load_scheduler_module(tmp_path)
    assert module._LOADER_PARALLELISM_AUTO_DEFAULTED is True
    with (
        patch.object(module, "PIPELINES", {"test_pipeline": [shorthand]}),
        patch.object(module, "_check_loader_dependencies", return_value=True),
        patch.object(module, "reap_stale_running_loaders", return_value=[]),
        patch.object(module.subprocess, "Popen", return_value=_mock_proc()) as mock_popen,
    ):
        module.run_pipeline("test_pipeline")

    assert mock_popen.call_args.kwargs["env"]["LOADER_PARALLELISM"] == "2"


def test_financial_statements_not_overridden_despite_matching_constraint(tmp_path, monkeypatch):
    """financial_statements is NOT in _SEC_ONLY_HIGHER_PARALLELISM_LOADERS (see module
    docstring) - its all-mode ignores --parallelism, so an override would be a no-op."""
    monkeypatch.delenv("LOADER_PARALLELISM", raising=False)
    module = _load_scheduler_module(tmp_path)
    with (
        patch.object(module, "PIPELINES", {"test_pipeline": ["financial_statements"]}),
        patch.object(module, "_check_loader_dependencies", return_value=True),
        patch.object(module, "reap_stale_running_loaders", return_value=[]),
        patch.object(module.subprocess, "Popen", return_value=_mock_proc()) as mock_popen,
    ):
        module.run_pipeline("test_pipeline")

    assert mock_popen.call_args.kwargs["env"]["LOADER_PARALLELISM"] == "1"


def test_operator_explicit_parallelism_never_overridden(tmp_path, monkeypatch):
    """An operator's own explicit LOADER_PARALLELISM must never be silently changed, even for
    a loader this module would otherwise bump to 2."""
    monkeypatch.setenv("LOADER_PARALLELISM", "1")
    module = _load_scheduler_module(tmp_path)
    assert module._LOADER_PARALLELISM_AUTO_DEFAULTED is False
    with (
        patch.object(module, "PIPELINES", {"test_pipeline": ["company_info"]}),
        patch.object(module, "_check_loader_dependencies", return_value=True),
        patch.object(module, "reap_stale_running_loaders", return_value=[]),
        patch.object(module.subprocess, "Popen", return_value=_mock_proc()) as mock_popen,
    ):
        module.run_pipeline("test_pipeline")

    assert mock_popen.call_args.kwargs["env"]["LOADER_PARALLELISM"] == "1"
