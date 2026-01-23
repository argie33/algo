# FRONTEND CONSISTENCY ENHANCEMENT

**Problem:** Some symbols show different metrics than others
- Stock A shows all 6 scores
- Stock B missing value_score
- Stock C missing quality_score
- Result: Inconsistent frontend display

**Root Cause:** Weight re-normalization when insufficient data
- If only 3 of 6 factors available, some scores left NULL
- Frontend shows what's available, hides NULLs

---

## SOLUTION: Consistent JSON Response Format

### BEFORE (Inconsistent)
```json
{
  "symbol": "AACG",
  "momentum_score": 44.65,
  "growth_score": 36.99,
  "value_score": null,           ← MISSING - confusing!
  "quality_score": 52.64,
  "positioning_score": 55.16,
  "stability_score": 27.17,
  "composite_score": 43.4
}
```

### AFTER (Consistent + Transparent)
```json
{
  "symbol": "AACG",
  "momentum_score": 44.65,
  "momentum_data_quality": "excellent",
  "growth_score": 36.99,
  "growth_data_quality": "good",
  "value_score": null,
  "value_reason": "insufficient_data",      ← ✅ NOW WE EXPLAIN
  "value_note": "Stock missing P/E and debt metrics needed for value calculation",
  "quality_score": 52.64,
  "quality_data_quality": "good",
  "positioning_score": 55.16,
  "positioning_data_quality": "excellent",
  "stability_score": 27.17,
  "stability_data_quality": "excellent",
  "composite_score": 43.4,
  "composite_confidence": "high",          ← ✅ HOW CONFIDENT IS THIS SCORE?
  
  "metadata": {
    "factors_used": 5,                     ← ✅ HOW MANY OF 6?
    "factors_total": 6,
    "weight_normalized": true,             ← ✅ IF NOT ALL FACTORS, WEIGHTS RE-NORMALIZED
    "missing_factors": ["value"],
    "calculation_date": "2026-01-22T18:46:39Z"
  }
}
```

---

## IMPLEMENTATION: Modify API Query

Change from this:
```sql
SELECT 
    symbol,
    momentum_score,
    growth_score,
    value_score,           -- Returns NULL if insufficient data
    quality_score,
    positioning_score,
    stability_score,
    composite_score
FROM stock_scores
WHERE symbol = 'AACG'
```

To this:
```sql
SELECT 
    symbol,
    momentum_score,
    growth_score,
    value_score,
    quality_score,
    positioning_score,
    stability_score,
    composite_score,
    
    -- Add explanations for NULLs
    CASE 
        WHEN value_score IS NULL THEN 'insufficient_data'
        WHEN value_score < 30 THEN 'very_low'
        WHEN value_score < 40 THEN 'low'
        ELSE 'normal'
    END as value_status,
    
    -- Data quality indicators
    (CASE WHEN momentum_score IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN value_score IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN quality_score IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN positioning_score IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN stability_score IS NOT NULL THEN 1 ELSE 0 END) as factors_available
FROM stock_scores
WHERE symbol = 'AACG'
```

---

## FRONTEND DISPLAY: Show Consistency

### Option 1: Show all metrics with badges
```
Momentum Score:   44.65 ✅ (100% data)
Growth Score:     36.99 ✅ (95% data)
Value Score:      —     ⚠️  (40% data - insufficient)
Quality Score:    52.64 ✅ (90% data)
Positioning:      55.16 ✅ (98% data)
Stability Score:  27.17 ✅ (95% data)
─────────────────────────────
Composite Score:  43.4  ⚠️  (5 of 6 factors)
```

### Option 2: Show all metrics, highlight NULLs
```
Momentum Score:   44.65
Growth Score:     36.99
Value Score:      [MISSING] → Why? Lacking P/E and debt data
Quality Score:    52.64
Positioning:      55.16
Stability Score:  27.17
─────────────────────────────
Composite Score:  43.4 (5 factors used, weights adjusted)
```

---

## BENEFITS

✅ **Consistency:** Every stock shows all 6 scores (or clear explanation why missing)
✅ **Transparency:** User understands why a score is NULL
✅ **Confidence:** Shows data quality/completeness for each metric
✅ **Debuggable:** Easy to see which factors are missing and why
✅ **Trust:** No hidden data - everything visible

---

## STATUS FIELD VALUES

Add a standardized `status` field for each score:

```
"momentum_status": "complete",     // Has all inputs
"growth_status": "complete",
"value_status": "partial",         // Has 4 of 6 inputs
"quality_status": "complete",
"positioning_status": "complete",
"stability_status": "complete",
"composite_status": "normalized"   // Weights re-adjusted for missing factor
```

---

## RECOMMENDED CHANGES TO loadstockscores.py

Add helper columns to stock_scores:
```sql
ALTER TABLE stock_scores ADD COLUMN (
    momentum_inputs_count INT,
    growth_inputs_count INT,
    value_inputs_count INT,
    quality_inputs_count INT,
    positioning_inputs_count INT,
    stability_inputs_count INT,
    total_inputs_count INT,
    score_completeness_pct INT
);
```

Then in API responses, return these alongside the scores.

