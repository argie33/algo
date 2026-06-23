# Validator Design: Leniency vs. Strictness

## Decision: Pydantic Lenient Mode (Type Coercion)

**Date:** 2026-06-23  
**Status:** DOCUMENTED - Current behavior maintained  
**Rationale:** User experience vs. strict type safety tradeoff

### Current Behavior

Pydantic validators in `models/requests.py` and `dashboard/response_validators.py` use **lenient mode**:

| Input | Type | Behavior | Example |
|-------|------|----------|---------|
| `"150.0"` | string | ✓ Coerces to `150.0` (float) | Entry price validation |
| `"5"` | string | ✓ Coerces to `5` (int) | Quantity validation |
| `"not_a_number"` | string | ✗ Rejects | Invalid data caught |
| `[150.0]` | list | ✗ Rejects | Type mismatch caught |
| `None` | null | ✗ Rejects (required fields) | Missing data caught |

### Why Lenient?

1. **Frontend flexibility:** JSON APIs often send `"123"` as strings due to JavaScript number serialization
2. **API usability:** Users sending `{"price": "150.50"}` should work, not fail
3. **Backward compatibility:** Existing integrations depend on this behavior
4. **Malformed data tests:** We now catch the truly malformed cases (wrong types) with comprehensive malformed data tests

### Tradeoff

- ✓ **Pro:** Better UX, fewer false failures, more forgiving
- ✗ **Con:** Developers might not catch type bugs early—caught instead by malformed data tests

### Safety Mechanism

**Malformed data tests ensure we catch real issues:**
- Test files with comprehensive malformed data coverage: 12 files
- Tests added: 89 tests specifically for wrong types, null, empty, negative values
- Real bugs found: 1 (AttributeError in `_format_phase_badge`)

### Files Using Lenient Validation

- `lambda/api/models/requests.py` - TradePreviewRequest, PositionUpdateRequest, etc.
- `dashboard/response_validators.py` - Portfolio, config, trade response validation
- `lambda/api/response_schema_validator.py` - Response type checking

### Files With Malformed Data Tests

✓ `tests/unit/test_request_validation.py` - 22 tests (Pydantic coercion documented)  
✓ `tests/integration/test_error_response_format.py` - 13 tests  
✓ `tests/unit/test_api_validation_integration.py` - 6 tests  
✓ Plus 6 additional test files with malformed coverage

### Future: If Strictness Needed

To switch to strict mode globally:
```python
# In Pydantic v2
class TradePreviewRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=False, validate_default=True)
    # Force str → str, int → int (no coercion)
```

**Cost:** Would require updating all 1000+ API calls from JavaScript/frontend.

---

## Recommendation

**Keep lenient validation** + **maintain comprehensive malformed data test coverage**.

This balances:
- User experience (lenient)
- Bug detection (malformed data tests)
- Test coverage (89+ new tests for edge cases)

