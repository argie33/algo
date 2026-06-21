# Phase 3: Loader Refactoring Guide

**Status**: Ready for Implementation | **Impact**: 70% violation reduction possible | **Effort**: 12-15 hours

## Quick Start

### Step 1: Identify Extraction Points
Find repeated `.get()` calls on the same dict type:
```python
# PATTERN: Multiple .get() on 'row' dict
high = row.get("high")
low = row.get("low")
close = row.get("close")
volume = row.get("volume")
# → Extract this!
```

### Step 2: Create Extraction Helper
Add to `utils/loaders/data_extractors.py`:
```python
def extract_technical_data_row(row: dict[str, Any]) -> dict[str, Any]:
    """Extract technical indicators from technical_data_daily row."""
    return {
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "volume": row.get("volume"),
        "sma_50": row.get("sma_50"),
        "sma_200": row.get("sma_200"),
        # ... all fields used in this loader
    }
```

### Step 3: Refactor Loader Method
```python
# BEFORE (10+ lines of defensive .get())
def process_row(self, row):
    high = row.get("high")
    low = row.get("low")
    close = row.get("close")
    if high is None or low is None:
        raise ValueError("Missing OHLC data")
    # ... 40 more lines of processing

# AFTER (clean, testable)
def process_row(self, row):
    data = extract_technical_data_row(row)
    if not self._validate_ohlc(data):
        raise ValueError("Missing OHLC data")
    return self._process_indicators(data)

def _validate_ohlc(self, data):
    return all(k in data and data[k] is not None 
               for k in ["high", "low", "close"])

def _process_indicators(self, data):
    # Clean 30-line method focused on logic only
    pass
```

### Step 4: Test & Commit
```bash
python -m mypy loaders/my_loader.py --ignore-missing-imports
python -m ruff check loaders/my_loader.py
pytest tests/test_my_loader.py -v
git add ... && git commit -m "refactor(loader): Extract [data type], split into sub-functions"
```

---

## Target Loaders (Priority Order)

### Priority 1: Quick Wins (2-4 hours each)
- **load_buy_sell_daily.py** (33 calls, 927 lines)
  - Extracts: technical_data_daily fields, market data context
  - Sub-functions: signal generation, validation, filtering
  
- **compute_circuit_breakers.py** (29 calls)
  - Extracts: position data, market metrics
  - Sub-functions: breaker calculation, threshold checks

- **load_stock_scores.py** (23 calls, ~600 lines)
  - Extracts: score components (momentum, quality, growth, etc.)
  - Sub-functions: per-factor scoring, aggregation

### Priority 2: Medium (4-6 hours each)
- **load_swing_trader_scores_vectorized.py** (17 calls)
- **load_signal_quality_scores.py** (13 calls)
- **load_cash_flow.py** (13 calls)

### Priority 3: Larger (6-8 hours each)
- **load_prices.py** (30 calls, 2613 lines)
  - Already well-structured class; focus on batch processing helpers
- **load_income_statement.py** (12 calls)
- **load_balance_sheet.py** (11 calls)

---

## Common Extraction Patterns

### Pattern 1: API Response Fields
```python
# loaders/data_extractors.py
def extract_price_response(response: dict) -> dict:
    """Extract OHLCV fields from yfinance or API response."""
    return {
        "open": response.get("Open"),
        "high": response.get("High"),
        "low": response.get("Low"),
        "close": response.get("Close"),
        "volume": response.get("Volume"),
        "adj_close": response.get("Adj Close"),
    }

# In loader:
price_data = extract_price_response(row)
if not all(price_data.values()):
    logger.warning(f"Incomplete price data: {price_data}")
    return None
```

### Pattern 2: Database Query Results
```python
# loaders/data_extractors.py
def extract_position_row(row: tuple) -> dict:
    """Extract position fields from database query result."""
    return {
        "symbol": row[0],
        "shares": row[1],
        "avg_cost": row[2],
        "current_price": row[3],
        "position_value": row[4],
    }

# In loader:
position = extract_position_row(db_row)
pnl = calculate_pnl(position)
```

### Pattern 3: Nested Config/Context
```python
# loaders/data_extractors.py
def extract_loader_config(batch_context: dict) -> dict:
    """Extract configuration from batch context."""
    return {
        "end_date": batch_context.get("end_date"),
        "parallelism": batch_context.get("parallelism", 2),
        "retry_limit": batch_context.get("retry_limit", 3),
        "log_level": batch_context.get("log_level", "INFO"),
    }

# In loader:
config = extract_loader_config(self._batch_context)
self._end_date = config["end_date"]  # Guaranteed to exist
self._parallelism = config["parallelism"]  # Has default
```

---

## Validation Checklist

For each refactored loader:

- [ ] All `.get()` calls consolidated into extraction helpers
- [ ] Sub-functions are < 50 lines each
- [ ] Error handling is explicit (fail-fast pattern)
- [ ] Extraction helpers are in utils/loaders/data_extractors.py
- [ ] Type hints on all functions
- [ ] Docstrings explain extraction purpose
- [ ] mypy passes with --ignore-missing-imports
- [ ] ruff check passes
- [ ] All tests pass
- [ ] No regressions vs baseline
- [ ] Commit message follows pattern: `refactor(loader): Extract [data], split into sub-functions`

---

## Expected Impact

### Per Loader
- **load_buy_sell_daily.py**: 33 → 5-8 violations (-75%)
- **compute_circuit_breakers.py**: 29 → 4-6 violations (-80%)
- **load_stock_scores.py**: 23 → 3-5 violations (-80%)

### Overall Loaders Category
- **Current**: 304 violations
- **After Phase 3**: ~60-80 violations (-75%)
- **Result**: Dashboard + Loaders = 460 violations (40% of codebase)

---

## Code Templates

### Extraction Helper Template
```python
def extract_MY_DATA_TYPE(data: dict[str, Any]) -> dict[str, Any]:
    """Extract [description] from [source].
    
    Called after error check to consolidate field access.
    All fields extracted here are safe to access without .get().
    """
    return {
        "field1": data.get("field1"),
        "field2": data.get("field2"),
        # ... more fields
    }
```

### Validation Helper Template
```python
def _validate_MY_DATA(self, data: dict) -> bool:
    """Validate required fields are present and non-null.
    
    Returns False immediately if any critical field is missing.
    Use before processing to fail-fast on incomplete data.
    """
    critical_fields = ["field1", "field2"]
    return all(data.get(f) is not None for f in critical_fields)
```

### Sub-function Template
```python
def _process_MY_LOGIC(self, data: dict) -> Any:
    """Process [specific aspect] of [domain].
    
    Extracted from larger method to improve testability.
    Single responsibility: [describe one thing this does].
    
    Args:
        data: Validated data dict from extraction helper
        
    Returns:
        Processed result (dict/list/value)
    """
    # 30-40 lines focused on one task
    result = self._transform(data)
    if not result:
        logger.debug(f"No result from {data}")
    return result
```

---

## Git Workflow for Phase 3

```bash
# 1. Pick a loader from Priority 1
git checkout -b refactor/loaders/load_buy_sell_daily

# 2. Create extraction helpers (if new data types)
# Edit: utils/loaders/data_extractors.py
# Add extract_technical_data_row(), extract_signal_context(), etc.

# 3. Refactor the loader
# Edit: loaders/load_buy_sell_daily.py
# - Replace .get() chains with extraction helpers
# - Extract validation into _validate_* methods
# - Split large methods into sub-functions

# 4. Validate
mypy loaders/load_buy_sell_daily.py --ignore-missing-imports
ruff check loaders/load_buy_sell_daily.py
pytest tests/test_load_buy_sell_daily.py -v

# 5. Commit
git add loaders/load_buy_sell_daily.py utils/loaders/data_extractors.py
git commit -m "refactor(load_buy_sell_daily): Extract technical data, split into sub-functions

- Add extract_technical_data_row() for 10+ field access consolidation
- Add extract_signal_context() for batch context parameters  
- Split _generate_signals() into focused: validate_ohlc, compute_indicators, apply_filters
- Result: 33 → 8 .get() violations, improved testability

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"

# 6. Push and create PR
git push -u origin refactor/loaders/load_buy_sell_daily
gh pr create --title "refactor(load_buy_sell_daily): Apply Phase 2 pattern" ...
```

---

## Prevention During Phase 3

✅ **Pre-commit checks remain active**
- Type checking via mypy catches schema mismatches
- Linting via ruff enforces style consistency
- Import validation prevents breakage

**No new .get() violations can be introduced** - pre-commit rejects commits with new defensive patterns

---

## Next: Algo Core (Phase 3b)

After loaders, apply same pattern to algo modules:
- **orchestrator/*.py** (100+ violations)
  - Extract: phase dependencies, execution state
  - Split: phase execution, validation, error handling
  
- **signals/*.py** (150+ violations)
  - Extract: signal components, market context
  - Split: per-signal scoring, filtering, consolidation

- **risk/*.py** (80+ violations)  
  - Extract: portfolio state, market data
  - Split: per-risk metric calculation, aggregation

---

## Support & Questions

1. **"How do I know what to extract?"**
   - Look for 3+ consecutive `.get()` calls on the same dict
   - Those are your extraction points

2. **"Should I extract single-use fields?"**
   - No. Extract groups of 3+ related fields used together
   - Single-use fields can stay as `.get()` inline

3. **"How do I test extraction helpers?"**
   ```python
   def test_extract_technical_data():
       row = {"high": 100, "low": 90, "close": 95}
       result = extract_technical_data_row(row)
       assert result["high"] == 100
       assert result.get("missing") is None  # Safe
   ```

4. **"What if extraction helper has 20+ fields?"**
   - Split into 2-3 helpers by logical domain
   - E.g., extract_price_fields(), extract_technical_indicators()

---

## Success Metrics

Phase 3 complete when:
- [ ] All Priority 1 loaders refactored (2-4 per person)
- [ ] Loaders violations reduced from 304 → <80
- [ ] All Priority 2 loaders started
- [ ] Extraction helpers framework mature
- [ ] Zero regressions in loader behavior
- [ ] Performance impact measured (should be 0% or positive)

**Estimated Timeline**: 2-3 engineers, 2-3 weeks to complete all Phase 3 work
