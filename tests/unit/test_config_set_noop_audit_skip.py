"""Regression test: AlgoConfig.set() must not write a no-op row to algo_config_audit
when the requested value is identical to the value already stored (old_value == new_value).

scripts/run_local_orchestrator.py calls config.set("execution_mode", "paper", "string")
unconditionally on every local dev orchestrator run (a paper-mode safety guard). Before
this fix, set() wrote an audit_log row on every call regardless of whether anything
changed, which had flooded algo_config_audit with ~1900 identical "paper -> paper" rows
(97% of the table) - burying real risk-parameter changes (e.g. the 2026-07-20
min_win_rate_pct restoration) under noise and defeating the audit trail's purpose.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from algo.infrastructure.config.main import AlgoConfig


def _make_config_with_mock_cursor(existing_value: str) -> tuple[AlgoConfig, MagicMock, MagicMock]:
    config = AlgoConfig.__new__(AlgoConfig)
    config._config = {}
    config._sources = {}

    mock_cur = MagicMock()
    mock_cur.fetchone.side_effect = [
        {"value": existing_value},  # old-value lookup
        [("value_type",)],  # has_value_type_col check
    ]
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    return config, mock_ctx, mock_cur


def _audit_insert_calls(mock_cur: MagicMock) -> list[Any]:
    return [c for c in mock_cur.execute.call_args_list if "algo_config_audit" in c.args[0]]


def test_set_same_value_skips_audit_insert() -> None:
    config, mock_ctx, mock_cur = _make_config_with_mock_cursor(existing_value="paper")

    with patch("algo.infrastructure.config.main.DatabaseContext", return_value=mock_ctx):
        result = config.set("execution_mode", "paper", "string")

    assert result is True
    assert _audit_insert_calls(mock_cur) == []


def test_set_changed_value_writes_audit_insert() -> None:
    config, mock_ctx, mock_cur = _make_config_with_mock_cursor(existing_value="paper")

    with patch("algo.infrastructure.config.main.DatabaseContext", return_value=mock_ctx):
        result = config.set("execution_mode", "dry", "string")

    assert result is True
    audit_calls = _audit_insert_calls(mock_cur)
    assert len(audit_calls) == 1
    assert audit_calls[0].args[1] == ("execution_mode", "paper", "dry", "system")
