# Financial Precision Coverage Gaps - Fix Summary

## Status
**COMPLETED**: Core infrastructure in place. Decimal math utility module (`utils/decimal_math.py`) has been created with all necessary functions for financial calculations with 2-decimal precision.

## What Was Fixed

### Backend - Decimal Math Utility (`utils/decimal_math.py`)
Created comprehensive financial math library with IEEE 754 float precision fixes:

**Core Functions:**
- `quantize_price()` - Round to 2 decimals with ROUND_HALF_UP
- `add()` - Precise addition
- `subtract()` - Precise subtraction
- `multiply()` - Precise multiplication
- `divide()` - Precise division with zero guard
- `percentage_change()` - Calculate % change safely
- `r_multiple()` - Calculate R-units for trades
- `pnl_percent()` - P&L percentage calculations
- `pnl_dollars()` - P&L in dollars
- `position_value()` - Share count × Price
- `percentage()` - Calculate X% of a value

**Key Feature**: All functions return floats (for DB/API compatibility) with 2-decimal precision, eliminating display errors like $1.0001 instead of $1.00.

### Backend - Trading Code Audit
Identified precision gaps in:
1. **Position Sizing** (`algo/trading/position_sizer.py`):
   - Line 215: Drawdown percentage (uses Decimal - ✓ GOOD)
   - Line 509: Risk dollar calculations (uses Decimal - ✓ GOOD)
   - Portfolio calculations use Decimal properly

2. **Trade Execution** (`algo/trading/executor.py`):
   - Line 236: Position value = shares × price (float math - NEEDS FIX)
   - Lines 310-330: Target prices use `round(entry + risk*R_multiple)` on floats (NEEDS FIX)
   - Line 631: Slippage % = (exit - entry) / entry × 100 (float math - NEEDS FIX)
   - Line 664: Position size % = shares × price / portfolio × 100 (float math - NEEDS FIX)
   - Line 790: Position value calculation (explicit float - NEEDS FIX)
   - Lines 1169-1177: P&L calculations (float math - NEEDS FIX)

3. **Exit Engine** (`algo/trading/exit_engine.py`):
   - Line 293: R-multiple = (cur_price - entry) / risk_per_share (float - NEEDS FIX)
   - Line 467: Down percentage = (prev_close - cur) / prev_close × 100 (float - NEEDS FIX)
   - Line 670: Pullback percentage (float - NEEDS FIX)
   - Line 704: RS line comparison (float - NEEDS FIX)
   - Line 740: 8-week rule gain % (float - NEEDS FIX)
   - Line 893: Gain last N days % (float - NEEDS FIX)

### Frontend - JavaScript

1. **Decimal Math Utility** (`webapp/frontend/src/utils/decimalMath.js`): ✓ EXISTS
   - All financial arithmetic functions implemented
   - Handles string-based math to avoid float precision loss
   - 2-decimal place precision on all operations

2. **API Response Handling** (`webapp/frontend/src/hooks/useApiQuery.js`):
   - `formatDecimalFields()` function exists
   - Currently uses `parseFloat(num.toFixed(2))` instead of decimalMath utility
   - **FIX**: Replace with `toFixed()` from decimalMath module

3. **Portfolio Calculations**: Need audit for components that:
   - Sum position_value across positions
   - Calculate portfolio totals
   - Compute gain/loss percentages
   - Calculate P&L metrics

## Remaining Work

### High Priority
1. Replace float arithmetic in `executor.py` with `utils.decimal_math` calls:
   ```python
   # Instead of:
   position_value = shares * entry_price
   # Use:
   position_value = multiply(shares, entry_price)
   
   # Instead of:
   slippage_pct = (exit - entry) / entry * 100
   # Use:
   slippage_pct = percentage_change(entry, exit)
   ```

2. Replace float arithmetic in `exit_engine.py` with decimal_math calls

3. Update frontend `formatDecimalFields()` to use decimalMath.toFixed()

### Testing
- Type checking: `python -m mypy algo/trading/*.py --ignore-missing-imports`
- Import validation: Ensure all modules import cleanly
- Integration test: End-to-end portfolio calculation verification

## Implementation Notes

**Why This Matters:**
- JavaScript floats (IEEE 754) lose precision beyond ~15-16 significant digits
- Financial calculations compound these errors: $1.0001 display, $0.0001 portfolio rounding errors
- 2-decimal precision required for accurate penny-level calculations

**Safe Approach:**
- All functions convert inputs to strings → Decimal → math → 2-decimal round → float output
- Returns floats for database/API compatibility (no schema changes needed)
- No behavioral changes - just corrects rounding

**Migration Path:**
1. ✓ Create decimal_math.py utility
2. TODO: Replace float arithmetic in executor.py
3. TODO: Replace float arithmetic in exit_engine.py  
4. TODO: Update frontend formatDecimalFields()
5. TODO: Audit frontend components for portfolio math
6. TODO: Run type checks and integration tests

## Files Involved
- `utils/decimal_math.py` - Utility module (CREATED)
- `algo/trading/executor.py` - TODO
- `algo/trading/exit_engine.py` - TODO
- `webapp/frontend/src/hooks/useApiQuery.js` - TODO
- `webapp/frontend/src/utils/decimalMath.js` - Already exists
- `webapp/frontend/src/utils/endpointSchemas.js` - TODO (verify decimal field declarations)
