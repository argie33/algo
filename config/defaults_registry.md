# Configuration Defaults Registry

**Purpose:** Document every hardcoded default value in the system, why it was chosen, and acceptable ranges.

**Last Updated:** 2026-06-13

---

## Data Freshness Defaults

### Staleness Windows (algo_data_patrol.py)
| Item | Default | Used When | Acceptable Range | Notes |
|------|---------|-----------|------------------|-------|
| price_daily | 7 days | Config not found | 1-30 days | Daily prices shouldn't be stale more than trading week |
| technical_data_daily | 7 days | Config not found | 1-30 days | Technical indicators need recent data |
| buy_sell_daily | 7 days | Config not found | 1-30 days | Signals must be recent |
| signal_quality_scores | 7 days | Config not found | 1-30 days | Quality scores age with market conditions |
| stock_scores | 14 days | Config not found | 7-60 days | Scores change more slowly |
| earnings_history | 120 days | Config not found | 30-365 days | Earnings data is less frequent |

**Risk:** If algo_config table is corrupted, system defaults to these values with no validation.

---

## Stop Loss & Risk Defaults

### Stop Loss Calculation (load_buy_sell_daily.py)
| Item | Default | Used When | Formula | Notes |
|------|---------|-----------|---------|-------|
| Default stop loss | 8% | Swing low not found | `close * 0.92` | Fallback when historical pivot missing |
| Risk % per trade | 8.0% | Standard signal | Used in reward ratio | Conservative 1:3 risk/reward target |

**Impact:** If swing low detection fails due to missing data, 8% is applied uniformly across all trades.

---

## Technical Indicator Limits

### DECIMAL(8,4) Database Constraints
| Metric | Max Value | Capping Method | When Exceeded |
|--------|-----------|-----------------|----------------|
| Volume surge % | 9999.9999 | `.clip()` | Extreme volume events |
| ROC (all periods) | ±9999.9999 | `.clip()` | Stock splits, extreme volatility |
| RSI | 100 (by definition) | N/A | Never exceeds |
| ADX | 100 (by definition) | N/A | Never exceeds |
| Mansfield RS | ±9999.9999 | `.clip()` | Extreme price moves |

**Logging:** ROC capping is logged when values exceed limits (load_technical_data_daily.py:223).

---

## Consolidation & Price Analysis

### Range Calculation (load_trend_criteria_data.py)
| Item | Default | Used When | Notes |
|------|---------|-----------|-------|
| Consolidation threshold | 10% | Price range < 10% over 10 days | Identifies tight-range stocks |
| Consolidation lookback | 10 days | Standard | Fixed window for range calculation |
| 52-week range window | 252 days | Used for high/low | Approx trading year |

**Risk:** Missing price data returns None instead of calculating range (safer than fake values).

---

## Data Source Age

### Technical Data Age Sentinel (load_technical_data_daily.py)
| Value | Meaning | Range | Notes |
|-------|---------|-------|-------|
| 0-999 | Trading days old | Valid | Actual age in trading days |
| -1 | Missing/Error | Sentinel | Indicates no data or exception |

**Reason:** Changed from 999 sentinel to -1 to distinguish between "999 days old" (real) and "data not found" (error state).

---

## Coverage Thresholds (algo_data_patrol.py)

### Universe Coverage
| Item | Threshold | Used When | Notes |
|------|-----------|-----------|-------|
| Min universe % | 75% | Patrol check | 75% of symbols must have data |
| Min coverage ratio | 0.75 | Field validation | 75% of records must have values |

### Loader Contracts (14-day windows)
| Item | Minimum | Notes |
|------|---------|-------|
| price_daily records | 40,000 | ~3,000 symbols × 13 trading days |
| buy_sell_daily records | 800 | ~60-70 symbols × 10-15 signals |
| coverage_ratio | 0.80 | 80% of symbols must provide signals |

---

## Feature Flags & A/B Testing (utils/feature_flags.py)

### Default Variants
| Test | Default Variant | Rationale |
|------|-----------------|-----------|
| A/B test fallback | "control" | Safe to apply to all users when flag undefined |

---

## Connection Pooling (webapp/frontend/...)

### Database Connection Pool (ThreadedConnectionPool)
| Setting | Value | Rationale |
|---------|-------|-----------|
| minconn | 2 | Minimum idle connections |
| maxconn | 15 | Prevent resource exhaustion (27 fetchers + 8 workers) |

---

## Parallelism Defaults (utils/loader_config.py)

| Loader | Default Parallelism | Notes |
|--------|------------------|-------|
| Generic | 1 | Safe default, prevents resource exhaustion |
| buy_sell_daily | Configured | See CLAUDE.md for job-specific settings |

---

## Signal Quality Fallback

### All-Zero Metrics Fallback (utils/fallback_registry.py)
| Metric | Fallback Value | Condition | Risk |
|--------|-----------------|-----------|------|
| total_trades | 0 | API failure + cache miss | Users see no activity |
| win_rate_pct | 0.0 | Both sources unavailable | Unclear if error or bad performance |
| sharpe_ratio | 0.0 | Rarely triggered | Misleading dashboard display |

**Mitigation:** Dashboard detects `_is_fallback_data` flag and displays warning.

---

## SEC Edgar API Fallback

### Ticker-to-CIK Mapping Cache (utils/sec_edgar_client.py)
| Data | Count | Fallback Condition | Staleness Risk |
|------|-------|--------------------|-----------------|
| Hardcoded ticker cache | 10,365+ entries | SEC API unavailable | Unknown version, no TTL |

**Risk:** New symbols added after code deploy won't be in hardcoded cache.

---

## Realtime Prices Fallback (algo/algo_realtime_prices.py)

### Market Hours Logic
| Scenario | Data Source | Risk |
|----------|-------------|------|
| 9:30 AM - 4:00 PM ET | Realtime API | Current |
| Before/after hours | Cached/daily prices | Stale (up to 16 hours old) |

**Mitigation:** Users must understand pre/post-market signals use previous close.

---

## Recommendations for Future Work

1. **Make all defaults configurable** - Move hardcoded values to `algo_config` table
2. **Add config audit trail** - Track when defaults were last reviewed
3. **Version compatibility** - Document which defaults are stable vs. experimental
4. **Environment-specific** - Different defaults for dev/staging/prod
5. **Quarterly review** - Audit this registry quarterly with business logic review

---

## Related Documentation

- `CLAUDE.md` - Project-wide configuration
- `steering/system.md` - System architecture and procedures
- `algo/algo_data_patrol.py` - Default configuration loader
- `utils/fallback_registry.py` - Fallback behavior documentation
