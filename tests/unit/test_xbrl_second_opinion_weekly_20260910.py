"""Tests for scripts/xbrl_second_opinion_weekly.py - the weekly ECS entrypoint that finally
gives layers 4/5 of the XBRL data-quality architecture (scripts/xbrl_yfinance_crosscheck.py,
scripts/xbrl_calculation_linkbase_check.py) an actual automated cadence instead of depending
on a human remembering to run them by hand.
"""

from unittest.mock import patch

import pytest


def _summary(n: int) -> dict:
    return {"sampled_symbols": n, "results": []}


class TestMain:
    def test_runs_both_layers_and_exits_zero_when_both_succeed(self) -> None:
        with (
            patch("scripts.xbrl_yfinance_crosscheck.run", return_value=_summary(25)) as yf_run,
            patch("scripts.xbrl_calculation_linkbase_check.run", return_value=_summary(15)) as calc_run,
        ):
            from scripts.xbrl_second_opinion_weekly import main

            with pytest.raises(SystemExit) as exc:
                main()

            assert exc.value.code == 0
            yf_run.assert_called_once_with(limit=25, symbols_override=None, dry_run=False)
            calc_run.assert_called_once_with(limit=15, symbols_override=None, dry_run=False)

    def test_one_layer_failing_does_not_prevent_the_other_from_running(self) -> None:
        with (
            patch("scripts.xbrl_yfinance_crosscheck.run", side_effect=RuntimeError("shared IP ban")) as yf_run,
            patch("scripts.xbrl_calculation_linkbase_check.run", return_value=_summary(15)) as calc_run,
        ):
            from scripts.xbrl_second_opinion_weekly import main

            with pytest.raises(SystemExit) as exc:
                main()

            assert exc.value.code == 0
            yf_run.assert_called_once()
            calc_run.assert_called_once()

    def test_both_layers_failing_exits_nonzero_for_operator_visibility(self) -> None:
        with (
            patch("scripts.xbrl_yfinance_crosscheck.run", side_effect=RuntimeError("boom")),
            patch("scripts.xbrl_calculation_linkbase_check.run", side_effect=RuntimeError("boom")),
        ):
            from scripts.xbrl_second_opinion_weekly import main

            with pytest.raises(SystemExit) as exc:
                main()

            assert exc.value.code == 1
