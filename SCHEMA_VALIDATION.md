# Schema Validation: Pre-Flight Type Checking

## Problem

Schema validation was checking only **column existence**, not **column types**. This meant:

- ✗ If a migration bug changed `price` from `NUMERIC` to `TEXT`, the loader would not detect it
- ✗ Data loading would fail at runtime with cryptic error messages (CSV parsing failures)
- ✗ Silent data corruption could occur if type coercion happened unexpectedly

Example failure scenario:
```
-- Migration bug: price column changed to TEXT
ALTER TABLE price_daily MODIFY COLUMN close TEXT;

-- Loader proceeds, then fails at COPY:
ERROR: invalid input syntax for type numeric: "abc"
```

## Solution

Added **type-aware pre-flight schema validation** that:

1. **Validates column types** before any data loading begins
2. **Catches schema mismatches** immediately with clear error messages
3. **Halts loader** if validation fails, preventing data corruption
4. **Is extensible** to other loaders via schema definitions

### Architecture

```
loaders/schema_definitions.py
    └─ TABLE_SCHEMAS: {table_name -> {col_name -> expected_type}}
    └─ PRICE_SCHEMA, ETF_PRICE_SCHEMA, etc.

utils/schema_validator.py
    ├─ validate_table_schema(cur, table, required_columns, check_row_count)
    │   └─ Returns (is_valid: bool, errors: List[str])
    ├─ _types_compatible(actual, expected)
    │   └─ Handles type aliases (numeric/decimal/float, int4/int8, etc.)

loaders/load_prices.py
    └─ _validate_schema_preflight()
        └─ Called at start of run() before fetching data
        └─ Raises RuntimeError if validation fails
```

## Usage

### For PriceLoader (Already Integrated)

The validation runs automatically at the start of `run()`:

```python
# loaders/load_prices.py
def run(self, symbols, parallelism=1, backfill_days=None):
    # PRE-FLIGHT VALIDATION runs here
    self._validate_schema_preflight()
    # ... rest of loading
```

### For Other Loaders

1. Add schema definition to `loaders/schema_definitions.py`:
```python
MY_LOADER_SCHEMA = {
    'symbol': 'varchar',
    'date': 'date',
    'value': 'numeric',
}

TABLE_SCHEMAS = {
    'my_table': MY_LOADER_SCHEMA,
    # ...
}
```

2. Call validation at start of loader.run():
```python
from utils.schema_validator import validate_table_schema
from loaders.schema_definitions import TABLE_SCHEMAS

def run(self, symbols):
    if self.table_name in TABLE_SCHEMAS:
        with DatabaseContext("read") as cur:
            is_valid, errors = validate_table_schema(
                cur,
                self.table_name,
                required_columns=TABLE_SCHEMAS[self.table_name],
                check_row_count=False
            )
            if not is_valid:
                raise RuntimeError(f"Schema validation failed: {errors}")
    # ... rest of loading
```

## Type Mapping

The validator understands PostgreSQL type aliases:

| Category | Types | Example |
|----------|-------|---------|
| **Numeric** | numeric, decimal, float4, float8 | `DECIMAL(12,4)` → accepted as `numeric` |
| **Integer** | int2, int4, int8, serial, bigserial | `BIGINT` → accepted as `integer` |
| **Text** | text, varchar, char, character | `VARCHAR(20)` → accepted as `text` |
| **Date** | date, timestamp, timestamptz | `TIMESTAMP` → accepted as `date` |
| **Boolean** | boolean, bool | `BOOL` → accepted as `boolean` |

## Error Messages

Clear, actionable error messages help diagnose schema issues:

```
[SCHEMA] ❌ Schema validation FAILED for price_daily:
Column 'close' in 'price_daily' has wrong type: 
expected 'numeric' but got 'text'. 
This will cause runtime failures when loading data.
```

## Testing

Run unit tests:
```bash
pytest tests/unit/test_schema_validation.py -v
```

Tests cover:
- Type compatibility checking
- Missing column detection
- Wrong type detection (the critical case)
- Table not found errors
- Type aliases (decimal, int4, etc.)

## Migration Path

When changing a column type:

1. **Before:** Only the table structure changes
2. **After:** Schema validation catches it immediately
3. **Logging:** Clear error message guides fix

Example:
```sql
-- Bad migration (will now be caught):
ALTER TABLE price_daily ALTER COLUMN close SET DATA TYPE TEXT;

-- Loader runs and fails with:
-- "Column 'close' has wrong type: expected 'numeric' but got 'text'"
```

## Performance

- Validation runs once per loader instance (at start of `run()`)
- Single SQL query to fetch column info
- Negligible overhead: <10ms typically

## Related Issues

- **ISSUE #5**: Schema validation for type safety
- **ISSUE #23**: Pre-flight checks before data loading

## Future Enhancements

- [ ] Add `nullable` validation (some columns required NOT NULL)
- [ ] Add `column_order` validation (if order matters for CSV parsing)
- [ ] Add `index` validation (ensure unique constraints exist)
- [ ] Extend to all major loaders (buy_sell, sentiment, economic data)
