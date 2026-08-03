"""Regression: _run_reconciliation_step()'s exception handler raised the literal string
"Paper mode reconciliation failed" in BOTH branches (paper-mode auth error and everything
else), regardless of actual execution_mode. A comment at the top of the try/except
documented a prior fix meant to stop mislabeling real live-mode ("auto") auth failures as
paper-mode - but that fix only changed which branch calls logger.error(); the raised
RuntimeError's message itself was never updated. A real Alpaca auth failure during live
trading (execution_mode="auto") - the highest-stakes case, since Phase 9 reconciliation
failure can gate a governance halt - still surfaced to on-call as "Paper mode
reconciliation failed", reading as an expected, non-critical local-dev condition.
"""

from datetime import date
from unittest.mock import patch

import pytest

from algo.orchestrator.phase9_reconciliation import _run_reconciliation_step


def test_live_mode_failure_is_not_labeled_paper_mode():
    config = {"execution_mode": "auto"}
    with patch("algo.infrastructure.reconciliation.DailyReconciliation") as mock_recon_cls:
        mock_recon_cls.return_value.run_daily_reconciliation.side_effect = RuntimeError(
            "401 Unauthorized - invalid Alpaca credentials"
        )
        with pytest.raises(RuntimeError) as exc_info:
            _run_reconciliation_step(config, date(2026, 8, 3), lambda *a, **k: None, dry_run=False)

    assert "Paper mode" not in str(exc_info.value), (
        f"live-mode (execution_mode=auto) reconciliation failure must not be mislabeled "
        f"'Paper mode reconciliation failed' - got: {exc_info.value}"
    )
    assert "auto" in str(exc_info.value)


def test_paper_mode_failure_is_still_labeled_paper_mode():
    config = {"execution_mode": "paper"}
    with patch("algo.infrastructure.reconciliation.DailyReconciliation") as mock_recon_cls:
        mock_recon_cls.return_value.run_daily_reconciliation.side_effect = RuntimeError(
            "401 Unauthorized - invalid Alpaca credentials"
        )
        with pytest.raises(RuntimeError) as exc_info:
            _run_reconciliation_step(config, date(2026, 8, 3), lambda *a, **k: None, dry_run=False)

    assert "Paper mode" in str(exc_info.value)
