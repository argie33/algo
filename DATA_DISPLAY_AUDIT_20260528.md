# Data Display Audit — Complete 68-Issue Analysis
**Date:** 2026-05-28 | **Status:** Ready for implementation

---

## Critical Issues (5) 🔴
1. **Technical columns NULL** in buy_sell_daily (ema_21, adx, mansfield_rs missing)
   - Root cause: load_signals_daily doesn't JOIN technical_data_daily
   - Trading impact: /api/signals returns incomplete indicator data

2. **Trend loader missing** (no weinstein_stage computation)
   - Root cause: load_trend_template_data.py not created
   - Trading impact: Market stage classification unavailable

3. **Symbol coverage S&P 500 only** (need Russell 2000/Midcap)
   - Root cause: Only 500 large-cap loaded, no Russell index loaders
   - Trading impact: Small/mid-cap opportunities invisible

4. **momentum_score NULL** (column exists but not populated)
   - Root cause: load_stock_scores.py doesn't compute momentum
   - Trading impact: Score-based filtering unavailable

5. **key_metrics empty** (market_cap and shares missing)
   - Root cause: load_key_metrics.py missing or not scheduled
   - Trading impact: Market cap displays NULL for all symbols

---

## High Priority (15) 🟠
**Metrics (6):** value_metrics, growth_metrics, positioning_metrics, stability_metrics, quality_metrics, key_metrics incomplete

**Signals (4):** adx, mansfield_rs, sma_50, sma_200 missing from buy_sell_daily

**Market (2):** VIX staleness not checked, trend stages incomplete

**API (3):** sentiment retry logic missing, FRED cache not implemented, signal themes not classified

---

## Medium Priority (28) 🟡
Loader status table, data monitoring, gap detection, coverage tracking, data quality, infrastructure

---

## Low Priority (20) 🔵
Code quality, documentation, logging, validation

---

## Effort Summary
| Category | Count | Est. Hours |
|----------|-------|-----------|
| Critical | 5 | 2.25 |
| High | 15 | 4.5 |
| Medium | 28 | 8 |
| Low | 20 | 6 |
| **TOTAL** | **68** | **20.75** |

**Critical path to trading ready: 135 minutes (Fix #1-5 only)**
