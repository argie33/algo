#!/usr/bin/env python3
"""
PHASE 8 BUG IDENTIFICATION
Tests the entry execution phase for actual bugs in production code
"""

import logging
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_stop_loss_calculation_bug():
    """Test stop loss calculation can produce negative values (BUG)."""
    print("\n=== TEST: Stop Loss Calculation Edge Cases ===")

    # SCENARIO: Extreme volatility (ATR very large)
    entry_price = 100.0
    atr = 150.0  # 150% of entry price!
    sma_50 = 50.0

    # This is the actual code from Phase 8, line 898-901
    stop_loss = min(
        sma_50 - atr,      # 50 - 150 = -100 (NEGATIVE!)
        entry_price - 2.0 * atr,  # 100 - 300 = -200 (NEGATIVE!)
    )

    print(f"Entry Price: ${entry_price}")
    print(f"ATR (volatility): ${atr}")
    print(f"SMA_50: ${sma_50}")
    print(f"Calculated Stop Loss: ${stop_loss}")

    if stop_loss < 0:
        print(f"[BUG CONFIRMED] Stop loss is negative (${stop_loss})!")
        print("   Impact: Cannot short stock at negative price")
        print("   Risk: Would crash position sizer or position tracker")
        return True

    # SCENARIO 2: High volatility but reasonable SMA
    entry_price = 100.0
    atr = 20.0
    sma_50 = 85.0

    stop_loss = min(
        sma_50 - atr,  # 85 - 20 = 65
        entry_price - 2.0 * atr,  # 100 - 40 = 60
    )

    print(f"\nEntry Price: ${entry_price}")
    print(f"ATR (volatility): ${atr}")
    print(f"SMA_50: ${sma_50}")
    print(f"Calculated Stop Loss: ${stop_loss}")

    if stop_loss > 0 and stop_loss < entry_price:
        print("[OK] Stop loss is reasonable")

    # SCENARIO 3: Zero entry price (would cause division by zero)
    entry_price = 0.0
    atr = 10.0
    sma_50 = 50.0

    print(f"\nEntry Price: ${entry_price}")
    print(f"ATR (volatility): ${atr}")
    print(f"SMA_50: ${sma_50}")

    try:
        # Line 903: risk_pct = (entry_price - stop_loss) / entry_price * 100
        if entry_price != 0:
            stop_loss = min(sma_50 - atr, entry_price - 2.0 * atr)
            risk_pct = (entry_price - stop_loss) / entry_price * 100
            print(f"Risk %: {risk_pct:.1f}%")
        else:
            print("[BUG] Zero entry price would cause ZeroDivisionError on line 903!")
            return True
    except ZeroDivisionError as e:
        print(f"[BUG CONFIRMED] ZeroDivisionError: {e}")
        return True

    return False

def test_risk_pct_calculation_bug():
    """Test risk_pct calculation with edge cases."""
    print("\n=== TEST: Risk Percentage Calculation ===")

    # SCENARIO: Negative stop loss (from previous bug)
    entry_price = 100.0
    stop_loss = -50.0  # Negative (impossible)

    print(f"Entry Price: ${entry_price}")
    print(f"Stop Loss: ${stop_loss}")

    # Line 903 code
    risk_pct = (entry_price - stop_loss) / entry_price * 100

    print(f"Risk %: {risk_pct:.1f}%")

    if risk_pct > 150:
        print("[ISSUE] Negative stop loss causes unrealistic risk %!")
        print("   Expected: 1-12%")
        print(f"   Got: {risk_pct:.1f}%")
        print("   Impact: Would be rejected by stop_too_wide check (line 912)")

    # SCENARIO: Very tight stop (rare but possible)
    entry_price = 100.0
    stop_loss = 99.0  # Only 1% risk

    risk_pct = (entry_price - stop_loss) / entry_price * 100
    print(f"\nTight Stop: Entry=${entry_price}, Stop=${stop_loss}")
    print(f"Risk %: {risk_pct:.1f}%")

    if risk_pct < 1.5:
        print("[INFO] Would be rejected as stop too tight (line 905-910)")

def test_position_sizer_type_bug():
    """Test if position sizer can receive wrong types."""
    print("\n=== TEST: Position Sizer Type Mismatch ===")

    # What if close price is integer from DB?
    close = 150  # int, not float
    atr = 10.5   # float
    sma_50 = 145.0  # float

    # Phase 8 casts to float (line 888)
    entry_price = float(close)
    atr = float(atr)
    sma_50 = float(sma_50)

    print(f"Entry Price type: {type(entry_price)} = {entry_price}")
    print(f"ATR type: {type(atr)} = {atr}")
    print(f"SMA_50 type: {type(sma_50)} = {sma_50}")

    # All converted to float - should be fine
    print("[OK] Type conversions successful")

def test_empty_technical_data():
    """Test behavior with empty technical data."""
    print("\n=== TEST: Empty Technical Data Handling ===")

    merged_technical_data = {}  # Empty!
    symbol = "AAPL"

    # Line 859: Check if symbol in cache
    if str(symbol) not in merged_technical_data:
        print(f"[OK] Empty cache detected, will skip {symbol}")

    # But what if the cache exists but has None values?
    merged_technical_data = {
        "AAPL": {
            "atr_14": None,
            "sma_50": None,
            "close": None
        }
    }

    tech_data = merged_technical_data.get("AAPL", {})
    atr = tech_data.get("atr_14")
    sma_50 = tech_data.get("sma_50")
    close = tech_data.get("close")

    print(f"ATR: {atr}, SMA_50: {sma_50}, Close: {close}")

    # Line 880 checks for this
    if close is None or atr is None or sma_50 is None:
        print("[OK] None values detected, will skip trade")

def test_position_value_overflow():
    """Test position sizing with large portfolio values."""
    print("\n=== TEST: Position Value Calculations ===")

    from decimal import Decimal

    # SCENARIO: Huge position sizing
    portfolio_value = Decimal('10000000000')  # $10 billion
    position_size_pct = Decimal('0.0075')  # 0.75% risk

    risk_dollars = portfolio_value * position_size_pct
    print(f"Portfolio: ${portfolio_value:,.0f}")
    print(f"Risk %: {position_size_pct * 100:.2f}%")
    print(f"Risk $ per trade: ${risk_dollars:,.2f}")

    # SCENARIO: Position per share calculation
    entry_price = Decimal('150')
    stop_loss = Decimal('140')
    risk_per_share = entry_price - stop_loss
    shares = int((risk_dollars / risk_per_share))

    print(f"Risk per share: ${risk_per_share}")
    print(f"Position size: {shares} shares")
    print(f"Position value: ${shares * entry_price:,.0f}")

    if shares * entry_price > portfolio_value * Decimal('2'):
        print("[ISSUE] Position >200% of portfolio (over-leveraged)!")

def test_phase_dependency_cascade():
    """Test what happens if Phase 7 returns empty signals."""
    print("\n=== TEST: Phase Dependency Cascade ===")

    qualified_trades = []  # Phase 7 returned nothing

    print(f"Qualified trades from Phase 7: {len(qualified_trades)}")
    print("[OK] Empty list is valid - can happen if no signals generated")
    print("   System should exit gracefully with 0 trades")

    # But what if we try to process empty list?
    entry_count = 0
    for signal in qualified_trades:
        entry_count += 1

    print(f"Entries executed: {entry_count}")
    print("[OK] Empty loop doesn't crash")

if __name__ == "__main__":
    print("=" * 70)
    print("PHASE 8 EDGE CASE BUG TESTS")
    print("=" * 70)

    bugs_found = []

    if test_stop_loss_calculation_bug():
        bugs_found.append("Stop loss can become negative")

    test_risk_pct_calculation_bug()
    test_position_sizer_type_bug()
    test_empty_technical_data()
    test_position_value_overflow()
    test_phase_dependency_cascade()

    print("\n" + "=" * 70)
    if bugs_found:
        print(f"BUGS FOUND: {len(bugs_found)}")
        for bug in bugs_found:
            print(f"  - {bug}")
    else:
        print("No critical bugs detected in basic tests")
