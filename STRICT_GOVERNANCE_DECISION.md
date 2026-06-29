# Strict Fail-Fast Governance Decision

**Date:** 2026-06-28  
**Status:** ✅ IMPLEMENTED

## The Conflict

Two objectives were in tension:

1. **User Goal:** "Get BREZ and similar stocks to show factor scores instead of '--' placeholders"
2. **Audit Principle:** "No silent fallbacks in finance—incomplete data is honest data"

## Decision: Strict Governance (No Fallbacks)

Chose to **enforce strict data requirements** rather than accept degraded data sources.

### Reverted Changes:
- ❌ Removed yfinance beta fallback for stocks <30 days history
- ❌ Removed 1-week momentum fallback for new stocks
- ✅ Keep explicit `data_unavailable` tracking for all metrics
- ✅ Keep WARNING-level logging for missing data

### New Governance Rules (Added to GOVERNANCE.md):

**Data Quality Principle:** Fail-fast on missing data. No silent fallbacks. Incomplete data is honest data.

**Strict Rules:**
1. Explicit `data_unavailable` flags on all metric records
2. Fail-fast when data insufficient (e.g., <30 days price history)
3. NO fallback to secondary data sources
4. NO single-metric composite scores (min_required_metrics ≥ 3)
5. WARNING-level logging for all missing data
6. Dashboard displays data_unavailable flags + completeness %

## Why This Approach

**In a trading system, incomplete data is a risk signal, not a bug to hide.**

- Single-metric scores (100% weight on one factor) bias position sizing
- Degraded data creates false confidence in composite scores
- Falling back to secondary data sources masks what data is actually available
- Traders need to know which stocks lack sufficient data to evaluate risk

## Result for BREZ

**Before governance:** Showed partial scores with fallbacks (misleading)

**After governance:** Shows '--' for factors it lacks data for (honest)
- Quality: -- (no SEC filings)
- Growth: -- (no SEC filings)
- Value: -- (no yfinance valuation data)
- Stability: -- (only 11 days price history)
- Momentum: -- (insufficient lookback)
- Positioning: ✓ (institutional ownership available)

**This is correct.** BREZ is a micro-cap IPO with legitimate data gaps.

## Trade-offs

**Tradeoff:** Fewer stocks scoring with complete metrics

**Benefit:** Scores that exist are reliable. Traders know exactly which stocks have incomplete data.

**Principle:** In finance, transparency > coverage.

## Governance Documentation

Added explicit "Data Quality" section to `steering/GOVERNANCE.md`:
- Why: Finance systems cannot hide incomplete data
- What: Strict rules against fallbacks
- How: Explicit flags, warning logs, fail-fast behavior

This prevents future developers from implementing "helpful" fallbacks that degrade accuracy.
