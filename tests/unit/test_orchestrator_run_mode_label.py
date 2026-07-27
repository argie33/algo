#!/usr/bin/env python3
"""Regression test for the orchestrator startup banner's run-mode label.

The banner is what an operator scans in logs to judge whether a run can touch real
money. It previously printed "LIVE" for any non-dry-run, including ordinary local
paper-mode test runs - indistinguishable from an actual real-money run. Only
execution_mode in ("live", "auto") combined with alpaca_paper_trading=False actually
risks real money.
"""

from algo.orchestration.orchestrator import compute_run_mode_label


class TestComputeRunModeLabel:
    def test_dry_run_always_labeled_dry_run(self):
        assert compute_run_mode_label(dry_run=True, execution_mode="live", alpaca_paper_trading=False) == "DRY RUN"
        assert compute_run_mode_label(dry_run=True, execution_mode="paper", alpaca_paper_trading=True) == "DRY RUN"

    def test_paper_execution_mode_labeled_paper(self):
        assert (
            compute_run_mode_label(dry_run=False, execution_mode="paper", alpaca_paper_trading=True) == "PAPER"
        )
        # Local dev sets execution_mode="paper" unconditionally, regardless of dry_run -
        # this is the exact scenario that previously mislabeled a local test run "LIVE".
        assert (
            compute_run_mode_label(dry_run=False, execution_mode="paper", alpaca_paper_trading=False) == "PAPER"
        )

    def test_auto_or_live_mode_with_paper_account_labeled_paper_not_live(self):
        # execution_mode="auto"/"live" with alpaca_paper_trading=True still routes to
        # Alpaca's paper endpoint - no real money at risk despite not being "paper" mode.
        assert (
            compute_run_mode_label(dry_run=False, execution_mode="auto", alpaca_paper_trading=True) == "PAPER"
        )
        assert (
            compute_run_mode_label(dry_run=False, execution_mode="live", alpaca_paper_trading=True) == "PAPER"
        )

    def test_auto_or_live_mode_with_real_account_labeled_real_money(self):
        assert (
            compute_run_mode_label(dry_run=False, execution_mode="auto", alpaca_paper_trading=False)
            == "LIVE - REAL MONEY"
        )
        assert (
            compute_run_mode_label(dry_run=False, execution_mode="live", alpaca_paper_trading=False)
            == "LIVE - REAL MONEY"
        )
