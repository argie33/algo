#!/usr/bin/env python3

"""
Trend signal methods — Minervini trend template, Weinstein stage, Mansfield RS.

NOTE: These methods are STUBS. Actual trend template and Weinstein stage
computations happen in load_trend_criteria_data.py (pre-computed daily and
stored in trend_template_data table). These stub methods are not used in the
main orchestrator pipeline. Orchestrator retrieves pre-computed scores from DB.

These stubs are left in place for future utility/standalone signal computation.
If needed, implement using canonical definitions from the loaders.
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SignalTrendMixin:
    """
    Trend signal stub methods. Not used in main orchestrator.

    Actual trend signal generation happens in loaders:
    - load_trend_criteria_data.py: Computes Minervini 8-point, Weinstein stage
    - Scores stored in trend_template_data table
    - Orchestrator evaluates pre-computed scores from DB
    """

    def minervini_trend_template(self, symbol: str, eval_date) -> Dict[str, Any]:
        """STUB: Actual implementation in load_trend_criteria_data.py"""
        raise NotImplementedError(
            "Minervini trend template is pre-computed by loaders. "
            "Retrieve from trend_template_data table instead."
        )

    def _minervini_empty(self, reason: str) -> Dict[str, Any]:
        """Helper for empty minervini response."""
        return {'score': 0, 'criteria': {}, 'pass': False, 'reason': reason}

    def weinstein_stage(self, symbol: str, eval_date) -> Dict[str, Any]:
        """STUB: Actual implementation in load_trend_criteria_data.py"""
        raise NotImplementedError(
            "Weinstein stage is pre-computed by loaders. "
            "Retrieve from trend_template_data table instead."
        )

    def mansfield_rs(self, symbol: str, eval_date, lookback: int = 200) -> Optional[float]:
        """STUB: Actual Mansfield RS implementation would use signal_base._rs_percentile_vs_spy()"""
        raise NotImplementedError(
            "Use SignalBase._rs_percentile_vs_spy() for Mansfield RS computation."
        )

    def stage2_phase(self, symbol: str, eval_date) -> Dict[str, Any]:
        """STUB: Use weinstein_stage() instead."""
        raise NotImplementedError("Use weinstein_stage() method instead.")
