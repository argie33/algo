#!/usr/bin/env python3
"""Edge case tests for VCP Patterns Loader - fail-fast behavior validation."""

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock
from loaders.load_vcp_patterns import VCPPatternsLoader


class TestVCPLoaderEdgeCases:
    """Test VCP loader fail-fast on data corruption."""

    def test_no_atr_data_raises_error(self):
        """No ATR data should raise RuntimeError."""
        loader = VCPPatternsLoader()
        cur = MagicMock()
        cur.fetchall.return_value = []

        with pytest.raises(RuntimeError, match="no ATR data"):
            loader._process_symbol(cur, "TEST", date(2026, 6, 27))

    def test_zero_atr_avg_raises_error(self):
        """Zero average ATR should raise RuntimeError."""
        loader = VCPPatternsLoader()
        cur = MagicMock()
        end_date = date(2026, 6, 27)
        cur.fetchall.return_value = [(end_date, 0.0)]

        with pytest.raises(RuntimeError, match="zero average ATR"):
            loader._process_symbol(cur, "TEST", end_date)

    def test_no_price_range_data_raises_error(self):
        """No price range data should raise RuntimeError."""
        loader = VCPPatternsLoader()
        cur = MagicMock()
        end_date = date(2026, 6, 27)

        atr_rows = [(end_date - timedelta(days=i), 14.5 - i * 0.05) for i in range(30)]
        cur.fetchall.side_effect = [atr_rows, []]

        with pytest.raises(RuntimeError, match="no price data"):
            loader._process_symbol(cur, "TEST", end_date)

    def test_null_price_range_raises_error(self):
        """NULL price ranges should raise RuntimeError."""
        loader = VCPPatternsLoader()
        cur = MagicMock()
        end_date = date(2026, 6, 27)

        atr_rows = [(end_date - timedelta(days=i), 14.5 - i * 0.05) for i in range(30)]
        range_rows = [(end_date - timedelta(days=i), None) for i in range(30)]
        cur.fetchall.side_effect = [atr_rows, range_rows]

        with pytest.raises(RuntimeError, match="NULL price ranges"):
            loader._process_symbol(cur, "TEST", end_date)

    def test_no_volume_data_raises_error(self):
        """No volume data should raise RuntimeError."""
        loader = VCPPatternsLoader()
        cur = MagicMock()
        end_date = date(2026, 6, 27)

        atr_rows = [(end_date - timedelta(days=i), 14.5 - i * 0.05) for i in range(30)]
        range_rows = [(end_date - timedelta(days=i), 2.5 - i * 0.01) for i in range(30)]
        cur.fetchall.side_effect = [atr_rows, range_rows, []]

        with pytest.raises(RuntimeError, match="no volume data"):
            loader._process_symbol(cur, "TEST", end_date)

    def test_null_volume_data_raises_error(self):
        """NULL volume data should raise RuntimeError."""
        loader = VCPPatternsLoader()
        cur = MagicMock()
        end_date = date(2026, 6, 27)

        atr_rows = [(end_date - timedelta(days=i), 14.5 - i * 0.05) for i in range(30)]
        range_rows = [(end_date - timedelta(days=i), 2.5 - i * 0.01) for i in range(30)]
        vol_rows = [(end_date - timedelta(days=i), None) for i in range(30)]
        cur.fetchall.side_effect = [atr_rows, range_rows, vol_rows]

        with pytest.raises(RuntimeError, match="NULL volume values"):
            loader._process_symbol(cur, "TEST", end_date)

    def test_zero_average_volume_raises_error(self):
        """Zero average volume should raise RuntimeError."""
        loader = VCPPatternsLoader()
        cur = MagicMock()
        end_date = date(2026, 6, 27)

        atr_rows = [(end_date - timedelta(days=i), 14.5 - i * 0.05) for i in range(30)]
        range_rows = [(end_date - timedelta(days=i), 2.5 - i * 0.01) for i in range(30)]
        vol_rows = [(end_date - timedelta(days=i), 0.0) for i in range(30)]
        cur.fetchall.side_effect = [atr_rows, range_rows, vol_rows]

        with pytest.raises(RuntimeError, match="invalid average volume"):
            loader._process_symbol(cur, "TEST", end_date)

    def test_valid_vcp_data_succeeds(self):
        """Valid data should compute VCP pattern successfully."""
        loader = VCPPatternsLoader()
        cur = MagicMock()
        end_date = date(2026, 6, 27)

        atr_rows = [(end_date - timedelta(days=i), 14.5 - i * 0.05) for i in range(30)]
        range_rows = [(end_date - timedelta(days=i), 2.5 - i * 0.01) for i in range(30)]
        vol_rows = [(end_date - timedelta(days=i), 1000000.0 + i * 10000) for i in range(30)]

        cur.fetchall.side_effect = [atr_rows, range_rows, vol_rows]

        loader._process_symbol(cur, "TEST", end_date)
        assert loader.symbols_failed == 0
