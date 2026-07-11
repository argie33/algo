# Metric Loader Consolidation Design

**Status:** Design Phase  
**Date:** 2026-07-11  
**Consolidating:** quality_metrics, growth_metrics, value_metrics, positioning_metrics, stability_metrics

## Problem Statement

Currently at 4:20 PM ET, we launch **6 independent ECS tasks**:
1. quality_metrics
2. growth_metrics  
3. value_metrics
4. positioning_metrics
5. stability_metrics
6. yfinance_snapshot

Each makes independent API calls to yfinance and SEC EDGAR for 3000+ symbols.

**Result:** 
- Redundant yfinance API calls (up to 18k requests vs 3k needed)
- Rate limiting when parallelism=2-5 per loader hits yfinance limits
- ~40-60 minute runtime across 5 loaders (most of it I/O wait)
- ~$0.03/day in wasted ECS compute

## Solution: Single Consolidated Loader

### Architecture Decision 1: Fetching Strategy

**CHOSEN: Two-tier fetch**

```
Tier 1: Fast data (yfinance) — 1 unified loader
  - Fetch once for all symbols
  - Cache in memory for all metric calculators
  - Parallelism = 5 (fast, I/O bound)
  - Timeout: 1800s (30 min)
  - Metrics computed from cache:
    * quality_metrics (ROE, debt_to_equity, margins)
    * value_metrics (P/E, P/B, P/S)
    * positioning_metrics (short interest)
    * stability_metrics (dividend yield)

Tier 2: Slow data (SEC EDGAR) — conditional, separate if needed
  - Only fetched if growth_metrics actually needs it
  - Parallelism = 1 (SEC has tight rate limits)
  - Timeout: 1800s separate
  - Metric computed:
    * growth_metrics (historical revenue/EPS growth)
```

**Why:** 
- yfinance is fast (100s/min), can handle 5x parallelism
- SEC EDGAR is slow (10-20s/min), can't parallelize beyond 1-2
- By separating, we get growth_metrics independently if yfinance fails
- Most metrics only need yfinance (80% of value)

### Architecture Decision 2: Class Structure

```python
class ConsolidatedMetricsLoader(OptimalLoader):
    """Load all metrics from unified yfinance fetch + optional SEC EDGAR."""
    
    table_name = "consolidated_metrics"  # For watermarking
    # But writes to 5 tables: quality_metrics, growth_metrics, value_metrics, etc.
    
    def run(self, symbols: list[str], since_date: date | None = None) -> dict:
        # Tier 1: Fetch yfinance once
        yfinance_data = self._fetch_yfinance_batch(symbols, parallelism=5)
        
        # Tier 1: Compute all metrics from cache
        quality = self._compute_quality_metrics(yfinance_data)
        value = self._compute_value_metrics(yfinance_data)
        positioning = self._compute_positioning_metrics(yfinance_data)
        stability = self._compute_stability_metrics(yfinance_data)
        
        # Insert all Tier 1 results (atomic transaction per metric table)
        self._insert_metrics('quality_metrics', quality)
        self._insert_metrics('value_metrics', value)
        # ... etc
        
        # Tier 2: Fetch SEC data (independent, can fail gracefully)
        try:
            sec_data = self._fetch_sec_batch(symbols, parallelism=1)
            growth = self._compute_growth_metrics(sec_data)
            self._insert_metrics('growth_metrics', growth)
        except TimeoutError:
            logger.warning("SEC EDGAR fetch timed out, marking growth_metrics data_unavailable")
            self._mark_data_unavailable('growth_metrics', symbols)
        
        return {
            'quality_metrics': len(quality),
            'value_metrics': len(value),
            'positioning_metrics': len(positioning),
            'stability_metrics': len(stability),
            'growth_metrics': len(growth),
        }
```

**Benefits:**
- Single entry point: ConsolidatedMetricsLoader
- Each metric computed independently (one fails → others still succeed)
- Clear separation of concerns (yfinance vs SEC)
- Reuses existing metric computation logic

### Architecture Decision 3: Error Handling

**Strategy: Graceful Degradation**

```
Scenario 1: yfinance fails completely
  → quality_metrics, value_metrics, positioning_metrics, stability_metrics = data_unavailable
  → growth_metrics = still attempted (uses SEC EDGAR)
  → Return partial success with unavailable flags

Scenario 2: SEC EDGAR fails
  → growth_metrics = data_unavailable
  → All yfinance metrics = still populated
  → Return partial success

Scenario 3: Symbol-specific failures
  → Per-symbol try/except
  → Failed symbols marked data_unavailable in that metric's table
  → Completed symbols inserted normally
  → Return completion_pct (e.g., 95% success)

Scenario 4: Database insert fails for one metric
  → Other metrics still inserted (separate transactions)
  → Failed metric marked with error, transaction rolled back
  → Phase 1 failsafe detects incomplete table, retries just that metric
```

**Implementation:**
```python
for symbol in symbols:
    try:
        # Per-symbol fetch + compute
        q = compute_quality(yfinance_data[symbol])
        g = compute_growth(sec_data[symbol])
    except (KeyError, ValueError) as e:
        logger.warning(f"Failed to compute metrics for {symbol}: {e}")
        mark_symbol_unavailable(symbol)
        continue
    
    results['quality'].append(q)
    results['growth'].append(g)

# Insert per-metric (one fails → others still inserted)
for metric_name, rows in results.items():
    try:
        db.insert(f'{metric_name}_metrics', rows)
    except DatabaseError as e:
        logger.error(f"Failed to insert {metric_name}: {e}, marking data_unavailable")
        mark_all_data_unavailable(metric_name, symbols)
```

### Architecture Decision 4: Parallelism & Timeouts

```
Tier 1 (yfinance):
  - CPU: 1024 (compute-intensive vectorized operations)
  - Memory: 2048 MB (hold all 3000+ symbols in dataframe)
  - Parallelism: 5 (yfinance handles 100 reqs/sec, so 5×3000 = 15k symbols/sec)
  - Timeout: 1800s (30 min, yfinance is slow)

Tier 2 (SEC EDGAR, conditional):
  - CPU: 512 (lighter, only if growth_metrics requested)
  - Memory: 1024 MB
  - Parallelism: 1 (SEC rate limit: 10-20 reqs/sec)
  - Timeout: 1800s (30 min, SEC filing parse is slow)

Overall ECS task config:
  - consolidated_metrics: { cpu=1024, memory=2048, timeout=3600, parallelism=5 }
```

**Rationale:**
- Higher parallelism on yfinance (it's fast, we underutilized it before)
- Lower parallelism on SEC (it's slow, we should respect rate limits)
- 3600s timeout = buffer for both tiers to complete

### Architecture Decision 5: Backwards Compatibility

**CHOSEN: Hard cutover (no stub loaders)**

Old loaders (load_quality_metrics.py, etc.) will:
1. Be moved to loaders/_deprecated/ for 2 weeks
2. Not be scheduled/invoked
3. Be deleted after successful production run

**Why:**
- Stub loaders create confusion (which one is running?)
- If consolidated loader fails, we need to manually trigger old ones anyway
- Clean break is safer than "maybe both running"
- Rollback: Restore from git history if needed

### Architecture Decision 6: Data Validation & Quality Checks

**Phase 1 Failsafe Integration:**
```
If consolidated_metrics returns <95% completion:
  → Phase 1 detects it's incomplete
  → Retries the ENTIRE consolidated_metrics loader (not individual metrics)
  → Why: Consolidated loader failure = upstream issue (yfinance/SEC)
  → Retrying the full loader fixes the root cause

Quality checks after load:
  - COUNT check: quality_metrics rows ≈ growth_metrics rows ≈ value_metrics rows
  - NULL check: Key fields (roe, pe_ratio, dividend_yield) not all NULL for symbol
  - Staleness check: updated_at should be today
```

## Implementation Checklist

### Phase 1: Implementation
- [ ] Create loaders/load_metrics_batch.py with ConsolidatedMetricsLoader class
- [ ] Implement _fetch_yfinance_batch() with parallelism=5
- [ ] Implement _compute_quality_metrics() from existing logic
- [ ] Implement _compute_growth_metrics() from existing logic
- [ ] Implement _compute_value_metrics() from existing logic
- [ ] Implement _compute_positioning_metrics() from existing logic
- [ ] Implement _compute_stability_metrics() from existing logic
- [ ] Implement per-metric insertion with separate transactions
- [ ] Add data_unavailable marking for failed metrics
- [ ] Add completion_pct calculation

### Phase 2: Infrastructure
- [ ] Update terraform: single "consolidated_metrics" loader config
- [ ] Update terraform: remove 5 individual metric loader configs
- [ ] Update terraform: remove yfinance_snapshot loader config
- [ ] Update lambda/trigger-loaders to recognize consolidated_metrics as critical
- [ ] Update Phase 1 failsafe to retry consolidated_metrics (not individual metrics)

### Phase 3: Testing
- [ ] Local: Run with --symbols AAPL,MSFT --limit 10
- [ ] Verify all 5 metric tables populated
- [ ] Compare old vs new output for same symbols
- [ ] Test error scenarios (yfinance timeout, SEC EDGAR timeout, etc.)
- [ ] Performance test: consolidated vs 5 sequential loaders
- [ ] Pre-commit: make format && make type-check

### Phase 4: Deployment
- [ ] Deploy terraform (new task definitions)
- [ ] Monitor first production run (tomorrow 4:20 PM)
- [ ] Verify all 5 tables populated
- [ ] Verify wall-clock time < 12 minutes
- [ ] Check CloudWatch: no errors in logs

### Phase 5: Cleanup
- [ ] Move old loaders to _deprecated/
- [ ] Create CONSOLIDATION_NOTES.md documenting changes
- [ ] Document rollback procedure
- [ ] Delete .bak files after 2 weeks of successful production runs

## Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Consolidated loader timeout | Low | High | Separate timeout per tier, graceful degradation |
| Data loss in old metric tables | Low | Critical | No deletion until prod verified, git history available |
| Phase 1 retry loop | Very Low | Medium | Clear separation of consolidated vs old loaders |
| Incomplete data for one metric | Medium | Low | Each metric has independent try/except, marks unavailable |
| Stock scoring fails | Low | Critical | stock_scores already handles data_unavailable flags |

## Success Criteria

1. ✅ Consolidated loader runs at 4:20 PM ET
2. ✅ All 5 metric tables populated with correct row counts
3. ✅ Wall-clock time for metrics phase < 12 minutes (vs ~40 min now)
4. ✅ yfinance API calls reduced by 80% (verifiable in logs)
5. ✅ No increase in data_unavailable flags
6. ✅ stock_scores completes successfully using consolidated metrics
7. ✅ Cost reduction: fewer ECS task invocations = lower bill
8. ✅ No regression in signal generation quality

## Timeline

- **Day 1:** Design (this document)
- **Day 2-3:** Implementation of load_metrics_batch.py + terraform updates
- **Day 4:** Local testing + pre-commit
- **Day 5+:** Deployment + monitoring
