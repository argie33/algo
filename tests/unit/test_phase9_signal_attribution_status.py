#!/usr/bin/env python3
"""Regression test for phase9_reconciliation._compute_signal_attribution's phase-result
status reporting.

SignalAttributionEngine is fully deprecated (algo/signals/attribution.py's own module
docstring: swing scores were removed, compute_ic() always returns every component marked
data_unavailable=True). Without a guard, the phase result unconditionally reported
"success, N components analyzed" even though nothing was ever actually analyzed, and
persist() wrote N new all-NULL rows to algo_component_attribution on every single Phase 9
run forever.
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _compute_signal_attribution


def _deprecated_ic_result(components: list[str]) -> dict[str, dict[str, object]]:
    return {
        comp: {
            "ic_value": None,
            "ic_pvalue": None,
            "sample_size": 0,
            "data_unavailable": True,
            "reason": "swing_components_deprecated",
        }
        for comp in components
    }


class TestSignalAttributionDeprecatedStatus:
    def test_all_unavailable_reports_warn_not_success(self):
        """When every component is data_unavailable, the phase result must not claim
        "success" - that misrepresents a fully deprecated, zero-analysis run as healthy."""
        log_calls = []

        def fake_log(phase_num, name, status, summary):
            log_calls.append((phase_num, name, status, summary))

        mock_engine = MagicMock()
        mock_engine.compute_ic.return_value = _deprecated_ic_result(["setup_quality", "trend_quality"])

        with patch("algo.signals.attribution.SignalAttributionEngine", return_value=mock_engine):
            _compute_signal_attribution(run_date=None, log_phase_result_fn=fake_log)

        assert len(log_calls) == 1
        _, name, status, summary = log_calls[0]
        assert name == "ic_computation"
        assert status == "warn", f"expected 'warn' for all-unavailable components, got {status!r}"
        assert "0/2" in summary or "0 components" in summary

    def test_all_unavailable_does_not_persist_null_rows(self):
        """persist() must not be called when there is nothing real to persist - avoids
        writing N all-NULL rows to algo_component_attribution every single run."""
        mock_engine = MagicMock()
        mock_engine.compute_ic.return_value = _deprecated_ic_result(["setup_quality"])

        with patch("algo.signals.attribution.SignalAttributionEngine", return_value=mock_engine):
            _compute_signal_attribution(run_date=None, log_phase_result_fn=lambda *a: None)

        mock_engine.persist.assert_not_called()

    def test_available_component_reports_success_and_persists(self):
        """When at least one component has real IC data, status is success and persist()
        is called - the guard must not suppress the legitimate/functional case."""
        log_calls = []

        def fake_log(phase_num, name, status, summary):
            log_calls.append((phase_num, name, status, summary))

        mock_engine = MagicMock()
        mock_engine.compute_ic.return_value = {
            "setup_quality": {"ic_value": 0.3, "ic_pvalue": 0.02, "sample_size": 40},
        }

        with patch("algo.signals.attribution.SignalAttributionEngine", return_value=mock_engine):
            _compute_signal_attribution(run_date=None, log_phase_result_fn=fake_log)

        mock_engine.persist.assert_called_once()
        _, _, status, summary = log_calls[0]
        assert status == "success"
        assert "1/1" in summary
