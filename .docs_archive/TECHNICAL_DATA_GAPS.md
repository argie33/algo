# Technical Data Quality Report
**Date:** 2026-04-26  
**Status:** Incomplete indicators identified - DO NOT BREAK existing loader work

---

## Current State

### Data AVAILABLE (Real, Populated)
✅ **RSI** - 4,868 stocks with data
✅ **ATR** - 4,868 stocks with data  
✅ **SMA 50** - 4,868 stocks with data
✅ **SMA 200** - 4,868 stocks with data
✅ **MACD** - Present in schema
✅ **Momentum (MOM)** - Present in schema
✅ **ROC variants** - Present in schema

### Data MISSING (NULL for All Stocks)
❌ **ADX** - 0/4868 stocks have data
❌ **EMA 21** - 0/4868 stocks have data  
❌ **Mansfield RS Rating** - 0/4868 stocks have data
❌ **Plus DI / Minus DI** - Present in schema but may be unpopulated

---

## Impact on Frontend

### Pages Affected
- **Trading Signals Detail:** Shows "—" for ADX, RS Rating, EMA fields
- **Stock Detail View:** Missing technical indicators shown as blank

### User Experience
When user views a stock detail page, they see:
```
Technical Indicators
✓ RSI: 20.66
✗ ADX: —
✓ ATR: 0.22
✗ RS Rating: —
✓ SMA 50: $10.32
✓ SMA 200: $12.58
✗ EMA 21: —
```

---

## Root Cause

The `technical_data_daily` table has these columns but **ADX, EMA, and RS Rating columns are always NULL** across all 4,868 stocks with technical data.

**Likely reasons:**
1. Original loader didn't calculate these indicators
2. Calculation failed partway through
3. These fields were skipped in data load process
4. Someone is working on combining these into another loader (DO NOT INTERRUPT)

---

## Action Required: NONE RIGHT NOW

**IMPORTANT:** Someone is already working on combining technical indicators into other loaders. Do NOT:
- Run new technical indicator loaders
- Modify technical_data_daily table directly
- Create workaround calculations

**DO:**
- Let the ongoing technical loader work complete
- Document what's missing for reference
- Only fix frontend to hide NULL values gracefully

---

## Frontend Fix (Safe - No DB Changes)

In `SignalCardAccordion.jsx`, add checks to only show indicators that have real data:

```javascript
// Before showing ADX, RS Rating, EMA - check if they're NULL
{signal.adx && <DataField label="ADX" value={signal.adx} />}
{signal.rs_rating && <DataField label="RS Rating" value={signal.rs_rating} />}
{signal.ema_21 && <DataField label="EMA 21" value={signal.ema_21} />}

// Instead of showing "—" for everything
```

---

## Database Inventory

### technical_data_daily Table
- **Rows:** 18.9M (16,173 per stock)
- **Columns with data:** RSI, ATR, SMA 20/50/200, MACD, MOM, ROC
- **Columns NULL:** ADX, EMA 12/26, RS Rating, Plus/Minus DI
- **Latest data:** 2026-04-24

### Status Summary
- ✅ Core technical data loaded
- ✅ Price moving averages working  
- ✅ Momentum/trend indicators available
- ⚠️ Advanced indicators incomplete
- 🔄 Someone working on completing these

---

## Waiting For

External work in progress:
- [ ] Technical indicator loader completion
- [ ] ADX calculation integration
- [ ] EMA calculation integration  
- [ ] RS Rating calculation integration
- [ ] Column population/refresh

**Do NOT modify until that work is merged.**

---

## Safe Frontend Workaround

**Option 1: Hide Empty Fields (No DB Changes)**
Update frontend to skip displaying NULL technical indicators instead of showing "—"

**Option 2: Add Backend Calculation (After Loader Work Done)**
Once complete technical data is loaded, API can return calculated values

**Current Recommendation:** Option 1 - just hide the empty fields gracefully while technical work completes.

---

**Status:** Monitoring for loader work completion. No action needed at this time.
