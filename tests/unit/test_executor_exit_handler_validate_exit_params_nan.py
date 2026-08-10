#!/usr/bin/env python3
"""Regression test for ExitHandler._validate_exit_params, found via a systematic sweep
for the NaN-comparison-guard bug class on 2026-08-10 (after fuzzing found 7 other
instances this session).

`exit_price <= 0` doesn't catch NaN (NaN comparisons are always False in Python), so a
NaN exit_price would silently pass this validation gate - the front-line guard for the
actual exit-execution path that closes real positions - as if it were valid.
exit_fraction's `0 < exit_fraction <= 1.0` chained comparison is naturally NaN-safe (the
first `0 < nan` comparison already evaluates False), but exit_price's single-sided check
was not.
"""

from unittest.mock import MagicMock

from algo.trading.executor_exit_handler import ExitHandler


class TestValidateExitParamsRejectsNanPrice:
    def test_nan_exit_price_rejected_not_silently_valid(self):
        result = ExitHandler._validate_exit_params(MagicMock(), exit_fraction=1.0, exit_price=float("nan"))
        assert result is not None
        assert result["success"] is False

    def test_infinite_exit_price_rejected(self):
        result = ExitHandler._validate_exit_params(MagicMock(), exit_fraction=1.0, exit_price=float("inf"))
        assert result is not None
        assert result["success"] is False

    def test_valid_exit_price_still_passes(self):
        result = ExitHandler._validate_exit_params(MagicMock(), exit_fraction=1.0, exit_price=100.0)
        assert result is None

    def test_nan_exit_fraction_already_correctly_rejected(self):
        """Sanity check: exit_fraction's chained comparison was already NaN-safe before
        this fix and must remain so."""
        result = ExitHandler._validate_exit_params(MagicMock(), exit_fraction=float("nan"), exit_price=100.0)
        assert result is not None
        assert result["success"] is False
