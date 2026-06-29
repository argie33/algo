#!/usr/bin/env python3
"""Tests for dashboard panel modules.

Verifies that panel modules exist and can be imported.
"""

import pytest


class TestPanelModulesExist:
    """Test that all panel modules can be imported."""

    def test_panel_base_imports(self):
        """Test panel base module imports."""
        from dashboard.panels import panel_base

        assert panel_base is not None
        assert hasattr(panel_base, "PanelBase")

    def test_portfolio_panel_imports(self):
        """Test portfolio panel module imports."""
        from dashboard.panels import portfolio

        assert portfolio is not None

    def test_health_panel_imports(self):
        """Test health panel module imports."""
        from dashboard.panels import health

        assert health is not None

    def test_market_panel_imports(self):
        """Test market panel module imports."""
        from dashboard.panels import market

        assert market is not None

    def test_signals_panel_imports(self):
        """Test signals panel module imports."""
        from dashboard.panels import signals

        assert signals is not None

    def test_exposure_panel_imports(self):
        """Test exposure panel module imports."""
        from dashboard.panels import exposure

        assert exposure is not None

    def test_positions_panel_imports(self):
        """Test positions panel module imports."""
        from dashboard.panels import positions

        assert positions is not None

    def test_trades_panel_imports(self):
        """Test trades panel module imports."""
        from dashboard.panels import trades

        assert trades is not None

    def test_circuit_panel_imports(self):
        """Test circuit breaker panel module imports."""
        from dashboard.panels import circuit

        assert circuit is not None

    def test_sectors_panel_imports(self):
        """Test sectors panel module imports."""
        from dashboard.panels import sectors

        assert sectors is not None

    def test_economic_panel_imports(self):
        """Test economic panel module imports."""
        from dashboard.panels import economic

        assert economic is not None


class TestPanelBaseAbstract:
    """Test PanelBase abstract class."""

    def test_panel_base_cannot_be_instantiated(self):
        """Test that PanelBase cannot be instantiated directly."""
        from dashboard.panels.panel_base import PanelBase

        # Should raise TypeError because format_content is abstract
        with pytest.raises(TypeError):
            PanelBase("test", "Test Panel")

    def test_panel_base_has_abstract_method(self):
        """Test that PanelBase defines abstract method."""
        from dashboard.panels.panel_base import PanelBase

        # Check that format_content is abstract
        assert hasattr(PanelBase, "format_content")
        assert getattr(PanelBase.format_content, "__isabstractmethod__", False)

    def test_panel_base_has_validate_inputs(self):
        """Test PanelBase has validate_inputs method."""
        from dashboard.panels.panel_base import PanelBase

        assert hasattr(PanelBase, "validate_inputs")

    def test_panel_base_has_render(self):
        """Test PanelBase has render method."""
        from dashboard.panels.panel_base import PanelBase

        assert hasattr(PanelBase, "render")


class TestCompactPanelBase:
    """Test CompactPanelBase."""

    def test_compact_panel_base_exists(self):
        """Test CompactPanelBase exists."""
        from dashboard.panels.panel_base import CompactPanelBase

        assert CompactPanelBase is not None

    def test_compact_panel_base_cannot_be_instantiated(self):
        """Test CompactPanelBase cannot be instantiated directly."""
        from dashboard.panels.panel_base import CompactPanelBase

        # CompactPanelBase is also abstract
        with pytest.raises(TypeError):
            CompactPanelBase("test", "Test")


class TestPanelStructure:
    """Test overall panel structure."""

    def test_panels_package_has_init(self):
        """Test panels package has __init__.py."""
        from dashboard import panels

        assert panels is not None

    def test_panel_helpers_exist(self):
        """Test panel helper modules exist."""
        from dashboard.panels import _helpers

        assert _helpers is not None

    def test_data_extractors_exist(self):
        """Test data extractors module exists."""
        from dashboard.panels import data_extractors

        assert data_extractors is not None
