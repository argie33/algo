# Fail-Fast Pattern for Financial Data

**Critical Principle**: In finance applications, silence is not acceptable. Missing data is NOT the same as zero or empty data.

## The Problem

Silent failures in financial systems lead to incorrect trading decisions:

```python
# ❌ BAD: Graceful degradation masks data problems
buy_signals = fetch_buy_signals()
for signal in buy_signals or []:  # Silently processes empty list if fetch fails
    execute_trade(signal)  # No indication data was missing
    
# ✅ GOOD: Fail-fast on missing data
buy_signals = fetch_buy_signals()
if buy_signals is None:
    raise FinanceValidationError("[BUY_SIGNALS] Data unavailable. Cannot proceed.")
for signal in buy_signals:
    execute_trade(signal)
```

## Core Principles

### 1. No Defaults for Critical Data

**Forbidden patterns**:
- `.get("key", default_value)` — Use explicit checks instead
- `value or []` / `value or {}` — Use explicit None validation
- `return None` on error — Raise exceptions
- Silent exception handling with logging only — Re-raise or fail-fast

**Accepted patterns**:
- `.get("optional_field", "")` for non-critical display data
- Explicit `if value is None: raise FinanceValidationError()`
- `try/except` that re-raises or converts to FinanceValidationError

### 2. Data Availability vs. Zero Data

These are NOT the same:

| Scenario | Representation | Handling |
|----------|-----------------|----------|
| Missing price data | `None` | **Raise error** |
| Price is zero | `0.0` | **Raise error** (invalid) |
| Zero dividend | `0.0` | Acceptable (no dividend) |
| Zero open positions | `0` | Acceptable with `allow_zero=True` |
| Missing signals | `None` | **Raise error** |
| No signals found | `[]` | Acceptable (empty result) |

### 3. Error Propagation Path

```
Data Source
    ↓
[Validation Layer]  ← strict_get_dict(), strict_get_float(), etc.
    ↓ (raises on error)
Loader/Fetcher
    ↓ (re-raises as RuntimeError)
Pipeline Stage
    ↓ (catches and logs context)
Trading Logic
```

Each layer is responsible for:
1. **Data Source**: Return None on unavailable, raise on corrupt
2. **Validation Layer**: Check for None/invalid, raise FinanceValidationError
3. **Loaders**: Convert to RuntimeError with context
4. **Pipeline**: Catch and log/alert, don't hide
5. **Trading**: Assume data is valid (already validated)

## Implementation Guide

### For Data Loaders

```python
from utils.finance_data_validation import strict_get_float, strict_get_dict

def fetch_prices():
    """Fetch prices from database. Raises if data unavailable."""
    with DatabaseContext("read") as cur:
        try:
            # Fetch data
            cur.execute("SELECT * FROM price_daily...")
            rows = cur.fetchall()
            
            if rows is None:
                raise RuntimeError("[PRICES] Database returned None instead of empty list")
            
            validated = []
            for row in rows:
                # Use strict validation - will raise if any field missing/invalid
                close = strict_get_float(
                    row.get("close"),
                    source="close_price",
                    context=f"symbol={row.get('symbol')}"
                )
                validated.append(close)
            
            if not validated:
                raise RuntimeError("[PRICES] Query returned 0 rows (check date range)")
            
            return validated
            
        except Exception as e:
            if isinstance(e, RuntimeError) and "[" in str(e):
                raise  # Already formatted
            raise RuntimeError(f"[PRICES] Load failed: {e}") from e
```

### For Dashboard Panels

```python
from utils.finance_data_validation import strict_get_list

def render_signals_panel(buy_signals):
    """Render buy signals. Must not be None."""
    rows = []
    
    # FAIL-FAST: Must validate upstream
    if buy_signals is None:
        rows.append(Text.from_markup("[red]Buy signals data unavailable[/]"))
        return rows
    
    try:
        signals = strict_get_list(buy_signals, source="buy_signals")
    except FinanceValidationError as e:
        rows.append(Text.from_markup(f"[red]Signal data error: {e}[/]"))
        return rows
    
    for signal in signals:
        # Now safe to process
        score = signal.get("score", 0)
        rows.append(Text(f"Signal: {score}"))
    
    return rows
```

### For Trading Logic

```python
from utils.finance_data_validation import strict_get_float, validate_before_trade

def calculate_position_size(price, portfolio_value):
    """Calculate position size. All inputs must be validated."""
    # Upstream must ensure these are not None/zero/invalid
    price = strict_get_float(price, source="entry_price", context="Entry calculation")
    portfolio = strict_get_float(portfolio_value, source="portfolio_value", context="Risk calculation")
    
    # Risk: 1% of portfolio per position
    risk_amount = portfolio * 0.01
    size = risk_amount / price
    
    # Validate before trade
    size = validate_before_trade(
        size, "position_size",
        lambda x: isinstance(x, (int, float)) and 0 < x < 100_000
    )
    
    return size
```

## Migration Guide

### From Old Code

```python
# OLD: Silent fallback
price = row.get("close", 0.0)  # Hides missing prices
if price:  # But zero prices fail silently
    execute_trade(price)

# NEW: Explicit validation
try:
    price = strict_get_float(
        row.get("close"),
        source="close_price",
        context=f"symbol={row['symbol']}"
    )
    execute_trade(price)
except FinanceValidationError as e:
    logger.error(f"Cannot execute trade: {e}")
    raise
```

### Pattern: From `.get()` to `strict_get_dict()`

```python
# OLD: Hides missing keys
symbol = data.get("symbol", "UNKNOWN")
value = data.get("value", 0.0)

# NEW: Fails on missing
symbol = strict_get_dict(data, "symbol", source="price_data")
value = strict_get_dict(data, "value", source="price_data")
```

### Pattern: From `or []` to `strict_get_list()`

```python
# OLD: Silently processes empty when data missing
for item in data or []:
    process(item)

# NEW: Fails if data missing
if data is None:
    raise FinanceValidationError("[DATA] Expected list, got None")
for item in strict_get_list(data):
    process(item)
```

## Testing Requirements

Every fail-soft pattern must have a test:

1. **Happy path test**: Valid data succeeds
2. **None test**: None input raises FinanceValidationError
3. **Invalid test**: Invalid data type raises FinanceValidationError
4. **Edge case test**: Zero/empty/boundary values handled correctly

```python
def test_position_size_calculation():
    # Happy path
    size = calculate_position_size(price=100.0, portfolio=10000.0)
    assert 0 < size < 100_000
    
    # None price raises
    with pytest.raises(FinanceValidationError):
        calculate_position_size(price=None, portfolio=10000.0)
    
    # Zero price raises
    with pytest.raises(FinanceValidationError):
        calculate_position_size(price=0.0, portfolio=10000.0)
    
    # None portfolio raises
    with pytest.raises(FinanceValidationError):
        calculate_position_size(price=100.0, portfolio=None)
```

## API Reference

See `utils/finance_data_validation.py`:

- `strict_get_dict(data, key, source="")` — Get dict value, raise on None or missing key
- `strict_get_list(data, source="")` — Validate list is not None
- `strict_get_float(value, source="", context="")` — Parse float, raise on None/zero/invalid
- `strict_get_int(value, source="", context="", allow_zero=False)` — Parse int, raise on None/invalid
- `require_non_empty_dict(data, source="")` — Validate dict not None and not empty
- `require_non_empty_list(data, source="")` — Validate list not None and not empty
- `validate_before_trade(value, field_name, validator)` — Generic validator for trade data

All raise `FinanceValidationError` on validation failure.

## Pre-Commit Checks

The codebase enforces this pattern via pre-commit hooks:

```bash
# Detects problematic patterns
- repo: local
  hooks:
    - id: check-no-silent-failures
      name: Detect silent failure patterns
      entry: python .pre-commit-scripts/check-fail-soft-patterns.py
      language: python
      types: [python]
      fail_fast: true
```

Patterns flagged:
- `or []` / `or {}` in data processing
- `.get()` with defaults for required fields
- `except.*: logger\.` followed by `continue` or `return`
- Missing `raise` after error condition

## References

- **Finance Data Validation**: `utils/finance_data_validation.py`
- **Tests**: `tests/test_fail_fast_finance_validation.py`
- **Error Handling Pattern**: `steering/ERROR_HANDLING.md`
- **API Standards**: `steering/GOVERNANCE.md` → API Error Responses section

## Questions?

If unclear whether data is critical:
1. Ask: "Could missing data cause incorrect trades?"
2. If yes → Must fail-fast with FinanceValidationError
3. If no (display-only) → Can have graceful degradation with logged warning

When in doubt, **fail-fast**. Silent data problems are catastrophic in finance.
