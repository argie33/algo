# Fail-Fast Quick Reference for Developers

**TL;DR**: Never silently fallback on missing financial data. Fail fast or return explicit markers.

---

## The Rule

Financial data flows MUST either:
1. **RAISE** an exception (for CRITICAL data), OR
2. **RETURN** an explicit marker dict (for OPTIONAL data)

## Quick Decision Tree

```
                         Missing data?
                              |
                    __________|__________
                   |                    |
              CRITICAL?            OPTIONAL?
              (prices, VIX,        (sentiment,
               volume, risk)        put/call)
                   |                    |
                RAISE                RETURN
              RuntimeError         data_unavailable
                or                     marker dict
               ValueError
```

---

## Code Examples

### ❌ WRONG: Silent Fallback
```python
def score_stock(symbol: str) -> float | None:
    metrics = fetch_metrics(symbol)
    if not metrics:
        return None  # ❌ WRONG: Silent failure
    return compute_score(metrics)
```

### ✅ CORRECT: Fail-Fast (CRITICAL Data)
```python
def score_stock(symbol: str) -> float:
    metrics = fetch_metrics(symbol)
    if not metrics:
        raise RuntimeError(
            f"[SCORE] Quality metrics unavailable for {symbol} — "
            f"cannot compute score for critical path"
        )
    return compute_score(metrics)
```

### ✅ CORRECT: Explicit Marker (OPTIONAL Data)
```python
def fetch_sentiment(symbol: str) -> dict[str, Any]:
    try:
        sentiment = api.get_sentiment(symbol)
        if not sentiment:
            logger.debug(f"[SENTIMENT] Unavailable for {symbol}")
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": "sentiment_api_no_data"
            }
        return {"sentiment_score": sentiment, "data_unavailable": False}
    except Exception as e:
        logger.debug(f"[SENTIMENT] Error for {symbol}: {e}")
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": f"error: {type(e).__name__}"
        }
```

---

## Checklist for Your Code

### Before Committing

- [ ] No `return None` without explicit `data_unavailable` marker
- [ ] No `return []` without explicit reason
- [ ] No `return {}` without explicit reason
- [ ] No `.get()` with defaults for:
  - Passwords, API keys, tokens
  - Risk metrics (thresholds, limits)
  - Price/volume data
- [ ] All database errors raised (not silently ignored)
- [ ] All API errors logged and handled (not silently ignored)

### For Loaders

```python
# ❌ WRONG
def fetch_incremental(self, symbol: str, since: date | None):
    data = query_data(symbol)
    if not data:
        return []  # Silent fallback

# ✅ CORRECT
def fetch_incremental(self, symbol: str, since: date | None):
    data = query_data(symbol)
    if not data:
        logger.debug(f"[LOADER] No data available for {symbol}")
        return [{
            "symbol": symbol,
            "data_unavailable": True,
            "reason": "no_source_data",
            "created_at": datetime.now(timezone.utc).isoformat()
        }]
    return format_records(data)
```

### For Config Access

```python
# ❌ WRONG (allows silent fallback)
threshold = config.get("risk_limit_pct", 50)

# ✅ CORRECT (fails if missing)
threshold = config.get("risk_limit_pct")
# OR (explicit default only for non-critical)
timeout = config.get("api_timeout_seconds", 30)  # OK for timeout
```

### For API Responses

```python
# ❌ WRONG
{
    "price": 123.45,
    "sentiment": sentiment_value or None  # No marker
}

# ✅ CORRECT
{
    "price": 123.45,
    "sentiment": sentiment_value,
    "sentiment_data_unavailable": sentiment_unavailable,
    "sentiment_unavailable_reason": reason
}
```

---

## Pre-Commit Hook Commands

Run before pushing:

```bash
# All enforcement hooks
python .pre-commit-scripts/check-silent-fallbacks.py
python .pre-commit-scripts/check-credential-defaults.py
python .pre-commit-scripts/check-dashboard-get-pattern.py

# Type safety
mypy --strict algo/ loaders/ lambda/

# Natural enforcement
pre-commit run --all-files
```

---

## Severity Levels

### CRITICAL Data (MUST fail-fast)
- Prices (open, high, low, close)
- Volume
- VIX / Market indices
- Circuit breaker flags
- Risk metrics (portfolio value, position sizing)
- Trade execution data

**Pattern**: Raise RuntimeError or ValueError

### HIGH-PRIORITY Data (Pre-flight validation + fail if <threshold)
- Quality metrics (ROE, margins, ratios)
- Growth metrics (EPS growth, revenue growth)
- Value metrics (P/E, P/B, P/S ratios)
- Stability metrics (volatility, beta)

**Pattern**: Pre-flight check, raise if <50% available

### OPTIONAL Data (Return explicit markers)
- Sentiment scores
- Put/call ratio
- Yield curve slope
- Industry rankings
- Positioning data

**Pattern**: Return `{"data_unavailable": True, "reason": "..."}`

---

## Common Mistakes

### Mistake 1: Empty Default for Critical Data
```python
# ❌ WRONG
volume = get_volume(symbol) or 0  # Hides missing data
if volume == 0:  # Can't distinguish missing from zero volume
    ...

# ✅ CORRECT
volume = get_volume(symbol)  # Raises if None
if volume == 0:  # Real zero is OK, missing would have raised
    ...
```

### Mistake 2: None Check Without Context
```python
# ❌ WRONG
metrics = fetch_metrics(symbol)
if metrics is None:
    return None  # Silent; caller doesn't know why

# ✅ CORRECT
metrics = fetch_metrics(symbol)
if metrics is None:
    raise RuntimeError(
        f"[METRICS] {symbol}: upstream loader failed or table empty. "
        f"Check {table} and loader CloudWatch logs."
    )
```

### Mistake 3: Optional Data Without Marker
```python
# ❌ WRONG
sentiment = fetch_sentiment(symbol)
return {"sentiment": sentiment}  # Is None? Caller doesn't know if unavailable

# ✅ CORRECT
sentiment = fetch_sentiment(symbol)
return {
    "sentiment": sentiment,
    "sentiment_data_unavailable": sentiment is None,
    "reason": "..." if sentiment is None else None
}
```

### Mistake 4: Config Defaults for Critical Values
```python
# ❌ WRONG
max_position_size = config.get("max_position_pct", 10)  # Silent if missing

# ✅ CORRECT
max_position_size = config.get("max_position_pct")  # Raises if missing
```

---

## Testing Your Code

Add test for missing data:

```python
def test_missing_data_fails_fast(self):
    """Verify that missing CRITICAL data raises, not returns None."""
    with pytest.raises(RuntimeError):
        loader.fetch_incremental("UNKNOWN", None)

def test_optional_data_returns_marker(self):
    """Verify that OPTIONAL data returns explicit marker."""
    result = fetcher.fetch_sentiment("UNKNOWN")
    assert result["data_unavailable"] is True
    assert "reason" in result
    assert result.get("sentiment") is None
```

---

## Ask for Help

**If unsure whether data is CRITICAL or OPTIONAL:**
- Ask in #data-governance or #risk-team
- Check `steering/GOVERNANCE.md` section "Data Classification"
- Look for existing similar loaders and copy their pattern

**If you hit a pre-commit violation:**
- Run the specific hook to see details:
  ```bash
  python .pre-commit-scripts/check-silent-fallbacks.py
  ```
- Check line numbers and context
- Fix and re-test

---

**Last Updated**: 2026-06-29  
**Author**: Fail-Fast Enforcement Team  
**Related**: FAIL_FAST_ENFORCEMENT_STATUS.md, CLAUDE.md, GOVERNANCE.md
