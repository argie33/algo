# Signal Rejection Categories

**Purpose:** Document all signal rejection reasons for explainability and Phase 5 filtering.

**Last Updated:** 2026-06-13

---

## Pre-Tier Rejections (Tier 0)

**These occur before signals enter the 5-tier filter pipeline.**

| Category | Reason | File | Impact |
|----------|--------|------|--------|
| technical_data_missing | Technical data unavailable for symbol/date | load_buy_sell_daily.py:104 | No signals generated at all |
| technical_data_incomplete_coverage | Technical data covers <70% of price symbols | load_buy_sell_daily.py:154 | All signals rejected until coverage improves |
| price_daily_incomplete_coverage | Price data covers <3000 symbols | load_buy_sell_daily.py:134 | All signals rejected until price coverage improves |
| data_source_age | Data too stale (>patrol_staleness_window) | algo_data_patrol.py | Quality check fails |
| missing_required_field | Missing OHLCV, volume, or technical indicator | load_buy_sell_daily.py | Individual signal skipped |

---

## Tier Rejections (Tiers 1-5)

**These are categorized by the 5-tier signal quality filter.**

### Tier 1: Data Quality
| Reason | Condition | Notes |
|--------|-----------|-------|
| missing_ohlcv | Open, High, Low, or Close is None | No valid entry/exit |
| zero_price | Price is exactly 0 | Invalid market data |
| missing_volume | Volume data unavailable | Can't assess participation |
| rsi_missing | RSI indicator not calculated | Technical breakdown |
| moving_avg_missing | SMA50, SMA200, or EMA21 missing | Can't assess trend |
| atr_missing | ATR (volatility) not available | Can't size risk |
| consolidation_unknown | Can't determine if in consolidation | Data gap |

### Tier 2: Market Health
| Reason | Condition | Notes |
|--------|-----------|-------|
| market_closed | Outside 9:30-16:00 ET | Pre/post-market signal |
| low_volume_day | Volume < 50% of 20d avg | Weak participation |
| extreme_volatility | ATR > 10% of close | Unusual risk conditions |
| no_trend_phase | Price doesn't match any of 4 trend stages | Sideways/chopping |

### Tier 3: Trend Confirmation
| Reason | Condition | Notes |
|--------|-----------|-------|
| price_below_sma200 | Close < 200-day moving average | Downtrend/weak |
| rsi_below_30 | RSI < 30 with bearish signal | Oversold but selling |
| breakout_too_small | Breakout < 1% above pivot | Not enough momentum |
| low_adx | ADX < 25 (weak trend) | Lack of directional conviction |

### Tier 4: Signal Quality
| Reason | Condition | Notes |
|--------|-----------|-------|
| low_strength | Signal strength < 0.5 (50%) | Poor technical quality |
| bad_risk_reward | Risk/reward ratio < 1:2 | Unfavorable odds |
| pivot_stale | Swing high/low > 20 bars ago | Entry level outdated |
| volume_surge_too_small | Volume surge < 50% | Weak participation |

### Tier 5: Portfolio Health
| Reason | Condition | Notes |
|--------|-----------|-------|
| position_limit_reached | Already holding max positions | Portfolio cap hit |
| sector_overweight | Sector already at max allocation | Diversification rule |
| correlation_high | Stock correlates > 0.8 with existing | Reduce redundancy |
| max_drawdown_risk | Portfolio drawdown > threshold | Risk tolerance |

---

## Data-Driven Rejection Patterns

### High Frequency Rejections by Reason
These patterns indicate system health issues:

| Pattern | Cause | Action |
|---------|-------|--------|
| 90%+ Tier 1 rejections | Data quality issue | Check DB completeness (price_daily, technical_data_daily) |
| 70%+ Tier 2 rejections | Market conditions | Normal on low-volume days, check for data gaps |
| 80%+ Tier 3 rejections | Extended bearish period | Market in downtrend (Stage 3-4) |
| 60%+ Tier 4 rejections | Low volatility period | Sideways market reduces signal quality |
| 40%+ Tier 5 rejections | Portfolio fully deployed | Portfolio at capacity |

---

## Rejection Tracking via Phase 5

### Query Examples

**Count signals rejected by reason for debugging:**
```sql
SELECT 
  rejection_reason,
  COUNT(*) as count,
  ARRAY_AGG(DISTINCT symbol ORDER BY symbol) as symbols
FROM filter_rejection_log
WHERE eval_date = CURRENT_DATE
  AND rejection_reason IS NOT NULL
GROUP BY rejection_reason
ORDER BY count DESC;
```

**Get rejection funnel for health monitoring:**
```sql
SELECT 
  COUNT(*) as total,
  SUM(CASE WHEN tier_1_pass THEN 1 ELSE 0 END) as t1_pass,
  SUM(CASE WHEN tier_2_pass THEN 1 ELSE 0 END) as t2_pass,
  SUM(CASE WHEN tier_3_pass THEN 1 ELSE 0 END) as t3_pass,
  SUM(CASE WHEN tier_4_pass THEN 1 ELSE 0 END) as t4_pass,
  SUM(CASE WHEN tier_5_pass THEN 1 ELSE 0 END) as t5_pass
FROM filter_rejection_log
WHERE eval_date = CURRENT_DATE;
```

**Find why specific symbol was rejected:**
```sql
SELECT 
  symbol, eval_date, rejection_reason,
  tier_1_pass, tier_1_reason,
  tier_2_pass, tier_2_reason,
  tier_3_pass, tier_3_reason,
  tier_4_pass, tier_4_reason,
  tier_5_pass, tier_5_reason
FROM filter_rejection_log
WHERE symbol = 'AAPL' AND eval_date = CURRENT_DATE;
```

---

## New Rejection Categories (To Implement)

**From audit recommendations:**

| Category | Purpose | File |
|----------|---------|------|
| volume_surge_capped | Volume surge exceeded 9999.9999% | load_buy_sell_daily.py |
| roc_capped | ROC values capped to ±9999.9999 | load_technical_data_daily.py |
| missing_swing_pivot | No valid swing high/low found | load_buy_sell_daily.py |
| fallback_data_used | Signal generated with fallback metrics | algo_position_monitor.py |
| estimated_price_used | Stop loss based on estimated price | phase7_reconciliation.py |

---

## Related Systems

- `utils/filter_rejection_tracker.py` - Rejection logging
- `algo/algo_data_patrol.py` - Data quality checks
- `loaders/load_buy_sell_daily.py` - Pre-tier rejection logging
- `tools/dashboard/panels.py` - Display rejection stats
