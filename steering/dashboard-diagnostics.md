# Dashboard Data Diagnostics Guide

## Overview

The algo dashboard relies on real-time data from multiple APIs and database loaders. When data is missing or stale, the dashboard should surface these issues clearly instead of showing placeholder/fallback values.

This guide helps you:
1. **Diagnose** which data sources are failing
2. **Understand** why they're failing  
3. **Fix** the root causes
4. **Verify** fixes work end-to-end

## Quick Start: Diagnose Your Data Issues

### 1. Run the Diagnostic Tool

```bash
# AWS mode (default) - shows all data fetcher issues
python -m tools.dashboard.diagnose_dashboard

# Or with verbose output to see full responses
python -m tools.dashboard.diagnose_dashboard --verbose

# Local development mode
python -m tools.dashboard.diagnose_dashboard --local
```

The tool will show:
- ✓ **SUCCESS**: Data successfully loaded (shows field count)
- ⚠ **STALE**: Data is too old (loader hasn't run recently)
- ✗ **ERRORS**: API call failed or validation failed
- ⚡ **MISSING FIELDS**: Data returned but some fields are None

### 2. Interpret the Report

**Example output:**
```
SUMMARY
  ✓ Success:        15
  ⚠ Stale:          2
  ✗ Errors:         3
  ⚡ Missing fields: 1
```

This means:
- 15 endpoints working fine
- 2 endpoints have stale data (e.g., portfolio hasn't been refreshed in >5 days)
- 3 endpoints throwing errors (network, validation, auth failures)
- 1 endpoint returning partial data (some expected fields are None)

## Troubleshooting by Issue Type

### ✗ ERRORS (API Failures)

**Common causes:**
1. Network/connectivity issues
2. API endpoint not responding
3. Validation failure (missing required fields in API response)
4. Authentication failure (Cognito token expired)

**Resolution steps:**

```bash
# 1. Check if API is responding
curl https://api-url/api/health -H "Authorization: Bearer $TOKEN"

# 2. Check specific endpoint
curl https://api-url/api/algo/portfolio \
  -H "Authorization: Bearer $TOKEN" \
  -s | jq '.'

# 3. Check API logs in CloudWatch
# Navigate to AWS Console → CloudWatch → Logs → /aws/lambda/api-handler
# Look for 5xx errors or timeout patterns

# 4. Check database connectivity
# RDS console → Database → Connectivity & security
# Ensure security groups allow Lambda VPC access
```

**If API validation fails:**
- Check API response has all required fields (see `VALIDATORS` mapping in `response_validators.py`)
- Check field types match expected (e.g., number not string)
- See CLAUDE.md → "Dashboard API Validation Strategy" for critical fields

### ⚠ STALE (Data Too Old)

**Common causes:**
1. Scheduled loaders haven't run (e.g., daily batch jobs)
2. Loader failed silently
3. Data freshness threshold is very strict

**Resolution steps:**

```bash
# Check when data was last updated
# Portfolio: Check portfolio.last_run timestamp (should be < 5 days old)
# Market data: Check market_health.timestamp (should be < 24 hours old)
# Performance: Check performance.timestamp (should be < 1 hour old)

# Manually trigger missing loaders
# Example: Portfolio data is 5 days old, algo hasn't run

# Option 1: Trigger via GitHub Actions
gh workflow run manual-invoke-loaders.yml \
  -f loaders="portfolio,performance"

# Option 2: Run locally
python -m loaders.load_portfolio_snapshot
python -m loaders.load_performance_metrics
```

**Freshness thresholds:**
| Data | Max Age | Why |
|------|---------|-----|
| Portfolio | 5 days | Algo only runs on trading days; long weekend = 4 calendar days |
| Performance | 1 hour | Needs recent PnL data |
| Market data | 24 hours | Used for position sizing (overnight data ok) |
| Health/Status | 1 hour | Operational data |

### ⚡ MISSING FIELDS (Partial Responses)

**Meaning:** API returned successfully but some expected fields are None

**Example:** Portfolio returns `{total_portfolio_value: 50000, total_cash: None, position_count: 5}`

**Causes:**
1. Data hasn't been computed yet (e.g., daily returns before market close)
2. Loader query returned empty result
3. API doesn't populate field (check API documentation)

**Resolution:**

```bash
# 1. Query database directly to verify data exists
SELECT total_portfolio_value, total_cash, position_count 
FROM portfolio 
ORDER BY last_updated DESC LIMIT 1;

# 2. Check if NULL is expected for this field
# Some fields legitimately can be NULL (e.g., performance.equity_vals if no history)

# 3. If field should never be NULL, check loader logs
# AWS Console → CloudWatch → application logs
# Search for portfolio loader errors
```

## Critical Fields That Must Never Be None

These fields cause silent failures if missing:

| Endpoint | Critical Fields | Impact if Missing |
|----------|-----------------|-------------------|
| Portfolio | `total_portfolio_value`, `total_cash`, `position_count` | Can't display portfolio or size positions |
| Performance | `total_trades`, `winning_trades`, `losing_trades` | Win rate calculation fails |
| Market | `spy_close`, `vix_level` | Can't calculate position sizing |
| Config | `enable_algo`, `execution_mode`, `max_positions` | Safety gates disabled |

## How the Dashboard Surfaces Data Issues

### Error Panel (Top of Screen)

When data is missing, an **error panel** appears at the top showing:
- Red (✗) for hard errors
- Yellow (⚠) for stale data
- Number of failed endpoints
- Press [d] to expand and see full error details

### Per-Panel Error Handling

Each panel:
1. **Checks for errors first** (before trying to display data)
2. **Shows error message** if data unavailable
3. **Never shows placeholder values** (no fake dashes/zeros)

Example: If portfolio fails, panel shows:
```
[PORTFOLIO] fetch failed:
  Portfolio data conversion failed: VIX = -1 (must be > 0)
```

Not:
```
Portfolio: $0.00
```

## FAQ

**Q: Why am I seeing data errors instead of the dashboard?**
A: That's working correctly! The dashboard now surfaces data issues instead of masking them. Fix the root cause (stale loader, failed API call) and errors will disappear.

**Q: How do I know if an error is critical vs. informational?**
A: 
- Red borders = **critical data** (blocks core functionality)
- Yellow borders = **stale data** (old but usable)
- Check the error message for specific field name

**Q: Can I ignore some data errors?**
A: Check the field name. If marked as "optional" in the API contract, it's ok to skip. If marked "critical", you must fix it.

**Q: How do I reload all data?**
A: Run the diagnostic tool, note which loaders are failing, and trigger them:
```bash
# Reload all loaders
python -m loaders.load_portfolio_snapshot
python -m loaders.load_performance_metrics
python -m loaders.load_market_health_daily
python -m loaders.load_stock_signals
```

## Verification Checklist

After fixing issues, verify:

```bash
✓ Run diagnostic: python -m tools.dashboard.diagnose_dashboard
  - All critical fetchers show "Success" ✓
  - No red "ERRORS" section
  - No yellow "STALE" section (or acceptable age)

✓ Run dashboard: python -m tools.dashboard.dashboard
  - No error panel at top
  - All data visible (no placeholder dashes)
  - Portfolio values, positions count, performance metrics all show

✓ Run full test suite: pytest tests/ -k dashboard
  - All panel tests pass
  - Error boundary tests pass
```

## Debug Mode: Run Dashboard with Verbose Logging

```bash
# Set debug logging to see every API call and response
LOGLEVEL=DEBUG python -m tools.dashboard.dashboard -w 30

# Look for lines like:
# [DEBUG] API /api/algo/portfolio: fields with None value: [...]
# [WARNING] API /api/algo/performance stale (X min old, threshold: Y min)
```

## When to Update steering/dashboard-diagnostics.md

Update this file when:
- Adding new critical endpoints
- Changing freshness thresholds
- Discovering new failure patterns
- Adding new recovery procedures

**Do NOT put:** Live status, timestamps, incident logs, "as of" dates

## References

- `CLAUDE.md` → Dashboard API Validation Strategy
- `tools/dashboard/fetchers.py` → Fetcher implementations
- `tools/dashboard/error_boundary.py` → Error handling utilities
- `tools/dashboard/response_validators.py` → Field validation rules
