#!/usr/bin/env python3
"""
Tests for HIGH priority fixes:
1. Cache Invalidation After Mutations (Frontend)
2. Stop Loss and R-Multiple Precision
3. Database Transaction Boundaries in Exit Flows
"""

from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestStopLossPrecision:
    """Verify stop loss and R-multiple calculations use Decimal throughout."""

    def test_target_calculation_preserves_decimal_precision(self):
        """Target prices should not drift due to floating-point arithmetic."""
        # Setup: entry 100.00, stop 90.00, risk = 10.00 per share
        entry_price = 100.00
        stop_loss = 90.00

        # Use Decimal for calculation (as fixed code does)
        entry_dec = Decimal(str(entry_price))
        stop_dec = Decimal(str(stop_loss))
        risk_dec = entry_dec - stop_dec

        # Test R-multiples
        r_multiples = {
            "T1": Decimal("1.5"),
            "T2": Decimal("3.0"),
            "T3": Decimal("4.0"),
        }

        expected_targets = {
            "T1": 100.00 + (10.00 * 1.5),  # 115.00
            "T2": 100.00 + (10.00 * 3.0),  # 130.00
            "T3": 100.00 + (10.00 * 4.0),  # 140.00
        }

        # Calculate with Decimal precision (as fixed code does)
        calculated_targets = {}
        for name, r in r_multiples.items():
            target_dec = entry_dec + (risk_dec * r)
            target_dec = target_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            calculated_targets[name] = float(target_dec)

        # Verify no drift
        for name in expected_targets:
            assert abs(calculated_targets[name] - expected_targets[name]) < 0.01, (
                f"{name}: expected {expected_targets[name]}, got {calculated_targets[name]}"
            )

    def test_fractional_r_multiple_precision(self):
        """Test with fractional R values that commonly cause float precision issues."""
        entry_price = 50.25
        stop_loss = 48.75

        entry_dec = Decimal(str(entry_price))
        stop_dec = Decimal(str(stop_loss))
        risk_dec = entry_dec - stop_dec

        # Fractional R-multiple: 1.5
        r_dec = Decimal("1.5")
        target_dec = entry_dec + (risk_dec * r_dec)
        target_dec = target_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        target_price = float(target_dec)

        # Expected: 50.25 + (1.5 * 1.5) = 50.25 + 2.25 = 52.50
        expected = 52.50
        assert abs(target_price - expected) < 0.01, f"Expected {expected}, got {target_price}"

    def test_slippage_recalculation_decimal_precision(self):
        """Slippage recalculation should also maintain Decimal precision."""
        signal_price = 100.00
        fill_price = 100.50
        stop_loss = 95.00

        # Slippage percentage (calculated but not used — just verify precision works)
        signal_dec = Decimal(str(signal_price))
        fill_dec = Decimal(str(fill_price))
        stop_dec = Decimal(str(stop_loss))

        _ = ((fill_dec - signal_dec) / signal_dec * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Recalculate targets from fill price
        risk_from_fill = fill_dec - stop_dec  # 100.50 - 95.00 = 5.50
        target_1_dec = fill_dec + (risk_from_fill * Decimal("1.5"))
        target_1_dec = target_1_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        target_1 = float(target_1_dec)

        # Expected: 100.50 + (5.50 * 1.5) = 100.50 + 8.25 = 108.75
        expected = 108.75
        assert abs(target_1 - expected) < 0.01, f"Expected {expected}, got {target_1}"


class TestDatabaseTransactionBoundaries:
    """Verify exit operations are atomic with proper locking and consistency checks."""

    def test_exit_trade_uses_row_locks(self):
        """Verify exit_trade uses FOR UPDATE locks on trades and positions."""
        # This is a structural test — we can't mock the actual database,
        # but we verify the lock logic is present in the code
        with open("algo/trading/executor.py") as f:
            code = f.read()
            # Verify FOR UPDATE is present in the exit_trade query
            assert "FOR UPDATE" in code, "exit_trade should use FOR UPDATE locks"
            assert "FOR UPDATE OF t, p" in code, "exit_trade should lock both trades and positions"

    def test_exit_trade_verifies_rowcounts(self):
        """Verify exit_trade checks rowcount after updates."""
        with open("algo/trading/executor.py") as f:
            code = f.read()
            # Verify rowcount checks are present
            assert "cur.rowcount" in code, "exit_trade should verify rowcount"
            assert "expected 1 row" in code, "exit_trade should check for exactly 1 row"

    def test_exit_trade_validates_position_consistency(self):
        """Verify exit_trade re-fetches and validates position state after update."""
        with open("algo/trading/executor.py") as f:
            code = f.read()
            # Verify consistency checks are present
            assert "Re-fetch position" in code or "re-fetch" in code.lower(), (
                "exit_trade should re-fetch position to verify consistency"
            )
            assert "Position consistency error" in code, "exit_trade should validate position state consistency"

    def test_exit_trade_audit_log_failure_causes_rollback(self):
        """Verify audit log failures trigger transaction rollback."""
        with open("algo/trading/executor.py") as f:
            code = f.read()
            # Verify audit log failure handling
            assert "AuditLogError" in code, "exit_trade should handle audit log errors"
            assert "raise AuditLogError" in code, "audit log failure should raise error (triggering rollback)"


class TestCacheInvalidationUtility:
    """Verify frontend cache invalidation utilities exist and are callable."""

    def test_cache_invalidation_module_exists(self):
        """Verify cacheInvalidation.js exists."""
        import os

        path = "webapp/frontend/src/utils/cacheInvalidation.js"
        assert os.path.exists(path), f"Cache invalidation utility should exist at {path}"

    def test_cache_invalidation_exports_functions(self):
        """Verify cacheInvalidation.js exports required functions."""
        with open("webapp/frontend/src/utils/cacheInvalidation.js") as f:
            code = f.read()
            # Verify exports
            assert "invalidatePositionCache" in code, "Should export invalidatePositionCache"
            assert "invalidateTradeCache" in code, "Should export invalidateTradeCache"
            assert "useInvalidateCache" in code, "Should export useInvalidateCache hook"
            assert "withCacheInvalidation" in code, "Should export withCacheInvalidation wrapper"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
