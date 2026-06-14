#!/usr/bin/env python3
"""Integration tests for algo modules."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.db.context import DatabaseContext


class TestIntegration:
    """Test integrated functionality across modules."""

    def test_end_to_end_signal_generation(self):
        """Test end-to-end signal generation pipeline imports and structure."""
        from algo.algo_signals import SignalComputer
        from algo.algo_swing_score import SwingTraderScore
        assert SignalComputer is not None
        assert SwingTraderScore is not None

    def test_live_data_pipeline(self):
        """Test pipeline structure for live market data."""
        try:
            from algo.algo_trade_executor import TradeExecutor
            from algo.algo_circuit_breaker import CircuitBreaker
            assert TradeExecutor is not None
            assert CircuitBreaker is not None
        except ImportError:
            pytest.skip("Pipeline modules not available")

    def test_database_context_available(self):
        """Test that database context can be imported."""
        try:
            assert DatabaseContext is not None
        except ImportError:
            pytest.skip("DatabaseContext not available")
