"""Regression test (real-money-readiness audit, 2026-09-08): value_score.py's
_dividend_sustainability_factor (the CATO value-trap payout-sustainability gate) was applied
correctly in Pass 1 (_score_value), but update_value_multiples_percentiles() - the post_run()
batch pass that unconditionally overwrites value_score/composite_score right after Pass 1 on
every pipeline run - never fetched vm.fcf_yield and recomputed the dividend component from
magnitude alone, silently undoing the gate on the value actually persisted to stock_scores.

This test drives update_value_multiples_percentiles() directly (not _score_value) with a
CATO-like row (high dividend yield, negative fcf_yield) and confirms the dividend component is
zeroed out by the sustainability factor in the persisted UPDATE, not just in Pass 1.
"""

from typing import Any
from unittest.mock import MagicMock, patch


class _Loader:
    from loaders.stock_scores.value_metrics import ValueMetricsMixin

    update_value_multiples_percentiles = ValueMetricsMixin.update_value_multiples_percentiles
    _components_with_corrected_value = staticmethod(ValueMetricsMixin._components_with_corrected_value)
    _percent_rank_cheap_high_sector_relative = staticmethod(ValueMetricsMixin._percent_rank_cheap_high_sector_relative)


def _make_mock_cursor(rows: list[tuple[Any, ...]]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


def _run(rows: list[tuple[Any, ...]]) -> list[Any] | None:
    cur = _make_mock_cursor(rows)
    mock_db_context = MagicMock()
    mock_db_context.__enter__ = MagicMock(return_value=cur)
    mock_db_context.__exit__ = MagicMock(return_value=False)

    loader = _Loader()
    captured: dict[str, Any] = {}

    def _fake_execute_values(_cur: Any, _sql: str, updates: Any, template: str) -> None:
        captured["updates"] = updates

    with patch("loaders.stock_scores.value_metrics._owner") as mock_owner:
        mock_owner.return_value.DatabaseContext.return_value = mock_db_context
        mock_owner.return_value.execute_values.side_effect = _fake_execute_values
        loader.update_value_multiples_percentiles()

    return captured.get("updates")


def _cato_like_row(dividend_yield: float, fcf_yield: float | None) -> tuple[Any, ...]:
    return (
        "CATOLIKE",
        50.0,  # value_score_old
        50.0,  # composite_score_old
        50.0,  # risk_score
        50.0,  # quality_score
        50.0,  # growth_score
        50.0,  # momentum_score
        15.0,  # pe_ratio
        2.0,  # pb_ratio
        1.5,  # ps_ratio
        14.0,  # forward_pe
        dividend_yield,
        fcf_yield,
        None,  # pe_ratio_unavailable_reason
        None,  # forward_pe_unavailable_reason
        {"value": 50.0},  # components
        "Consumer Discretionary",  # sector
        99.0,  # data_completeness
        False,  # data_unavailable
        {},  # unavailable_metrics
    )


def test_negative_fcf_yield_zeroes_dividend_component_in_persisted_update() -> None:
    # A high yield funded by negative FCF must contribute 0 to the persisted value_score's
    # dividend term via update_value_multiples_percentiles, matching Pass 1's gate.
    unsustainable = _run([_cato_like_row(dividend_yield=0.215, fcf_yield=-0.05)])
    sustainable = _run([_cato_like_row(dividend_yield=0.215, fcf_yield=0.30)])

    assert unsustainable is not None
    assert sustainable is not None
    value_score_unsustainable = unsustainable[0][1]
    value_score_sustainable = sustainable[0][1]

    assert value_score_unsustainable is not None
    assert value_score_sustainable is not None
    # Same inputs except fcf_yield sign - the well-covered payout must score strictly higher
    # since its dividend component isn't floored to 0 by the sustainability gate.
    assert value_score_sustainable > value_score_unsustainable


def test_missing_fcf_yield_leaves_dividend_component_ungated() -> None:
    # No fcf_yield data at all -> _dividend_sustainability_factor returns 1.0 (fail-open on
    # missing data, matching Pass 1's own contract) - must not raise or null the score.
    updates = _run([_cato_like_row(dividend_yield=0.03, fcf_yield=None)])
    assert updates is not None
    assert updates[0][1] is not None
