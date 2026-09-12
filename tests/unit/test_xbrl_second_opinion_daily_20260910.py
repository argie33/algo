"""Tests for scripts/xbrl_second_opinion_daily.py - the daily entrypoint that finally
gives layers 4/5/6 of the XBRL data-quality architecture (scripts/xbrl_yfinance_crosscheck.py,
scripts/xbrl_calculation_linkbase_check.py, scripts/xbrl_dqc_arelle_check.py) an actual
automated cadence instead of depending on a human remembering to run them by hand.

Layer 6 was added to this wrapper 2026-09-12 (previously fully unscheduled, cloud or
local). It has a different call shape (pick a rotating sample, then call run(symbols=...)
rather than run(limit=...)) - `_run_dqc_layer` adapts that to the uniform loop in main(),
so it's mocked at that adapter's own two internal calls (_select_rotating_sample, run)
rather than at the same layer as the other two.
"""

from unittest.mock import patch

import pytest


def _summary(n: int) -> dict:
    return {"sampled_symbols": n, "results": []}


def _dqc_summary(n: int) -> dict:
    return {"checked": n, "flagged_symbols": 0, "results": []}


class TestMain:
    def test_runs_all_three_layers_and_exits_zero_when_all_succeed(self) -> None:
        with (
            patch("scripts.xbrl_yfinance_crosscheck.run", return_value=_summary(25)) as yf_run,
            patch("scripts.xbrl_calculation_linkbase_check.run", return_value=_summary(15)) as calc_run,
            patch("scripts.xbrl_dqc_arelle_check._select_rotating_sample", return_value=["A"] * 10) as dqc_sample,
            patch("scripts.xbrl_dqc_arelle_check.run", return_value=_dqc_summary(10)) as dqc_run,
        ):
            from scripts.xbrl_second_opinion_daily import main

            with pytest.raises(SystemExit) as exc:
                main([])

            assert exc.value.code == 0
            yf_run.assert_called_once_with(limit=25, symbols_override=None, dry_run=False)
            calc_run.assert_called_once_with(limit=15, symbols_override=None, dry_run=False)
            dqc_sample.assert_called_once_with(10)
            dqc_run.assert_called_once_with(symbols=["A"] * 10, dry_run=False)

    def test_dry_run_flag_threads_through_to_every_layer(self) -> None:
        """BUG FIX 2026-09-13: main() previously had no argument parsing at all, so
        `--dry-run` was silently ignored and every layer always ran live - this is the
        regression test for that fix.
        """
        with (
            patch("scripts.xbrl_yfinance_crosscheck.run", return_value=_summary(25)) as yf_run,
            patch("scripts.xbrl_calculation_linkbase_check.run", return_value=_summary(15)) as calc_run,
            patch("scripts.xbrl_dqc_arelle_check._select_rotating_sample", return_value=["A"] * 10),
            patch("scripts.xbrl_dqc_arelle_check.run", return_value=_dqc_summary(10)) as dqc_run,
        ):
            from scripts.xbrl_second_opinion_daily import main

            with pytest.raises(SystemExit) as exc:
                main(["--dry-run"])

            assert exc.value.code == 0
            yf_run.assert_called_once_with(limit=25, symbols_override=None, dry_run=True)
            calc_run.assert_called_once_with(limit=15, symbols_override=None, dry_run=True)
            dqc_run.assert_called_once_with(symbols=["A"] * 10, dry_run=True)

    def test_dqc_adapter_uses_rotating_sample_when_no_override_given(self) -> None:
        """_run_dqc_layer itself (not just main()'s wiring) picks a fresh rotating
        sample when symbols_override is None, matching the other two layers' own
        `symbols_override=None` default-to-rotation behavior.
        """
        from scripts.xbrl_second_opinion_daily import _run_dqc_layer

        with (
            patch("scripts.xbrl_dqc_arelle_check._select_rotating_sample", return_value=["B"] * 5) as dqc_sample,
            patch("scripts.xbrl_dqc_arelle_check.run", return_value=_dqc_summary(5)) as dqc_run,
        ):
            summary = _run_dqc_layer(limit=5, symbols_override=None, dry_run=True)

            assert summary == {"sampled_symbols": 5}
            dqc_sample.assert_called_once_with(5)
            dqc_run.assert_called_once_with(symbols=["B"] * 5, dry_run=True)

    def test_one_layer_failing_does_not_prevent_the_others_from_running(self) -> None:
        with (
            patch("scripts.xbrl_yfinance_crosscheck.run", side_effect=RuntimeError("shared IP ban")) as yf_run,
            patch("scripts.xbrl_calculation_linkbase_check.run", return_value=_summary(15)) as calc_run,
            patch("scripts.xbrl_dqc_arelle_check._select_rotating_sample", return_value=["A"] * 10),
            patch("scripts.xbrl_dqc_arelle_check.run", return_value=_dqc_summary(10)) as dqc_run,
        ):
            from scripts.xbrl_second_opinion_daily import main

            with pytest.raises(SystemExit) as exc:
                main([])

            # Every layer still gets attempted, but a partial failure must still exit
            # nonzero - otherwise it never surfaces (Task Scheduler's LastTaskResult
            # locally, or the DLQ/CloudWatch alarm path in AWS) and silently degrades
            # back into "depends on a human noticing the logs."
            assert exc.value.code == 1
            yf_run.assert_called_once()
            calc_run.assert_called_once()
            dqc_run.assert_called_once()

    def test_dqc_layer_missing_arelle_install_does_not_prevent_the_others(self) -> None:
        """The DQC layer raises loudly (RuntimeError) rather than reporting a silent
        "clean" when Arelle/dqc_us_rules isn't installed (see xbrl_dqc_arelle_check.py's
        own module docstring) - this must be caught the same as any other layer failure,
        not let bubble up and abort the other two layers.
        """
        with (
            patch("scripts.xbrl_yfinance_crosscheck.run", return_value=_summary(25)) as yf_run,
            patch("scripts.xbrl_calculation_linkbase_check.run", return_value=_summary(15)) as calc_run,
            patch(
                "scripts.xbrl_dqc_arelle_check._select_rotating_sample",
                side_effect=RuntimeError("arelleCmdLine not found on PATH"),
            ),
        ):
            from scripts.xbrl_second_opinion_daily import main

            with pytest.raises(SystemExit) as exc:
                main([])

            assert exc.value.code == 1
            yf_run.assert_called_once()
            calc_run.assert_called_once()

    def test_all_layers_failing_exits_nonzero_for_operator_visibility(self) -> None:
        with (
            patch("scripts.xbrl_yfinance_crosscheck.run", side_effect=RuntimeError("boom")),
            patch("scripts.xbrl_calculation_linkbase_check.run", side_effect=RuntimeError("boom")),
            patch(
                "scripts.xbrl_dqc_arelle_check._select_rotating_sample",
                side_effect=RuntimeError("boom"),
            ),
        ):
            from scripts.xbrl_second_opinion_daily import main

            with pytest.raises(SystemExit) as exc:
                main([])

            assert exc.value.code == 1
