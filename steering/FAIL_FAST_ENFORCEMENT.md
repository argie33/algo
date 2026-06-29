# Fail-Fast Governance Enforcement & Monitoring

**Effective Date**: 2026-06-29  
**Status**: Active - Automated enforcement in place  
**Scope**: All Python code, especially financial data paths

---

## Why This Matters

Silent failures in financial applications are **unacceptable** because they:
- Skew position sizing calculations
- Hide data quality issues
- Allow trades to execute with incomplete risk data
- Make debugging impossible when things go wrong

This document describes the **automated enforcement system** that prevents these violations.

---

## The Problem We're Solving

Developers sometimes write code like this (BAD):

```python
# Returns None silently instead of raising
def fetch_yield_curve():
    try:
        return get_data()
    except Exception:
        logger.error("Fetch failed")
        return None  # ❌ Caller doesn't know it failed

# Uses .get() with defaults that hide missing data  
price = prices.get("close", 0)  # ❌ If price missing, silently defaults to 0

# Returns empty collection without context
if not rows:
    logger.warning("No data")
    return []  # ❌ Caller can't distinguish "no data" from "empty result"
```

**These patterns violate CLAUDE.md** and must be **rejected at commit time**.

---

## How Enforcement Works

### Layer 1: Pre-Commit Hooks (Local)
Before you commit, 6 hooks validate your code:

1. **check-credential-defaults.py**  
   Blocks: `secret.get("password", "")`  
   Prevents silent auth failures

2. **enforce-type-safety-rules.sh**  
   Blocks: Disabling critical Pylint checks  
   Ensures type safety across financial code

3. **check-dashboard-get-pattern.py**  
   Blocks: `.get()` without FetcherValidator in dashboard code  
   Prevents missing portfolio fields

4. **enforce-strict-safe-conversion.py**  
   Blocks: `safe_float(x)` without `strict=True` on financial fields  
   Ensures price/cash/position conversions are validated

5. **catch-unsafe-get-comparisons.py**  
   Blocks: Comparing `.get()` results without safe conversion  
   Prevents type errors in calculations

6. **block-seed-prices-in-orchestrator**  
   Blocks: Test data in production orchestrator Lambda  
   Prevents fake data from affecting live trades

### Layer 2: CI/CD Checks (Automated)
Every commit triggers `.github/workflows/daily-violation-scan.yml`:

```yaml
on:
  push:
    branches: [main, develop]  # Runs on every commit
  schedule:
    - cron: '0 9 * * *'        # Also runs daily at 9 AM
```

This workflow:
- ✅ Scans all critical financial paths
- ✅ Detects new violations
- ✅ Rejects PRs with violations
- ✅ Prevents SKIP= bypass

### Layer 3: Anti-Skip Enforcement
**SKIP= bypass is now blocked:**

```bash
# This will FAIL:
SKIP=check-credential-defaults git commit ...
# Error: Cannot skip critical governance hook
```

The `.pre-commit-scripts/prevent-skip.sh` hook rejects any attempt to bypass:
- check-credential-defaults
- enforce-type-safety-rules
- check-dashboard-get-pattern
- enforce-strict-safe-conversion

---

## Monitoring & Reporting

### Daily Scan
Run manually to check current state:

```bash
python scripts/daily_violation_scan.py
```

Output:
```
CRITICAL VIOLATIONS FOUND: 0
Critical financial paths are clean!
```

### Compliance Check
Verify pre-commit setup is correct:

```bash
python scripts/check_precommit_violations.py
```

Detects:
- Commits with SKIP= bypass
- Missing hook configuration
- Uninstalled local hooks

### Historical Dashboard
See trends over time:

```bash
python scripts/violation_dashboard.py
```

Shows:
- Violations fixed by date
- Which developers introduced violations
- Hook bypass frequency
- Trends over last 30 days

### Export Metrics
Integrate with monitoring systems:

```bash
python scripts/violation_dashboard.py --json-export
```

Returns JSON for Grafana, DataDog, etc.

---

## Violations That Are BLOCKED

These patterns will be caught and rejected:

### CRITICAL (Always rejected)
- ❌ `secret.get("password", "")` - credential defaults
- ❌ `return None` without raising (in critical paths)
- ❌ `price = data.get("close", 0)` - silent zero for prices
- ❌ `SKIP=any_hook git commit` - hook bypass

### HIGH (Rejected in critical paths)
- ❌ `return []` for financial data fetch
- ❌ `.get()` without FetcherValidator in dashboard
- ❌ `safe_float(x)` without `strict=True` on positions

---

## Violations That Are ALLOWED

These patterns pass validation because they're handled correctly:

### ✅ Explicit error raising
```python
# GOOD - raises exception, doesn't fail silently
if data_invalid:
    raise RuntimeError("Cannot proceed without valid data")
```

### ✅ Explicit data_unavailable markers
```python
# GOOD - returns marker so caller knows data is missing
if not price_data:
    return {"data_unavailable": True, "reason": "no_price_history"}
```

### ✅ Proper validation before .get()
```python
# GOOD - checks field exists before using .get()
required_fields = ["close", "volume"]
if not all(f in data for f in required_fields):
    raise ValueError("Missing required price fields")
close = data.get("close")  # Now safe
```

### ✅ Optional enrichment with clear markers
```python
# GOOD - sentiment is optional, explicitly marked when missing
sentiment = sentiment_data.get("score")  # None is OK for optional enrichment
if sentiment is None:
    logger.debug("Sentiment unavailable (optional enrichment)")
```

---

## What Happens If You Hit A Violation

### Scenario 1: Commit locally
```bash
$ git commit -m "Add price fetcher"

Linting Python files with ruff...
Type checking with mypy...
🔍 Checking imports...
❌ BLOCKED: check-credential-defaults

CRITICAL PATTERN DETECTED:
  File: loaders/new_loader.py:42
  Pattern: secret.get("api_key", "")
  
You cannot use .get() with empty string defaults for credentials.
Always validate explicitly:
  
  api_key = os.getenv("API_KEY")
  if not api_key:
      raise ValueError("API_KEY required")
```

**Fix**: Change the code to raise an exception instead.

### Scenario 2: Try to bypass with SKIP=
```bash
$ SKIP=check-credential-defaults git commit ...

ERROR: Cannot skip critical governance hook: check-credential-defaults
This hook is required to prevent fail-fast violations in financial data handling.

Reason you cannot skip:
  - Prevents empty-string defaults for passwords/API keys
  - Silent credential failures could bypass authentication

If you believe this hook is incorrectly blocking legitimate code,
contact the team to discuss whitelisting.
```

**Fix**: Fix the underlying issue, don't bypass the hook.

### Scenario 3: CI/CD detects violation
```
Daily Fail-Fast Violation Scan

CRITICAL VIOLATIONS FOUND: 1

loaders/price_transformer.py:320
  Severity: CRITICAL
  Impact: price data - position sizing
  Issue: returns [] without error
  Code: if not rows: return []

ACTION REQUIRED: Fix all critical violations before merge!
```

**Fix**: Update the code before PR is approved.

---

## For Developers

### Setup (First Time)
```bash
# Install pre-commit hooks locally
pre-commit install

# Verify installation
python scripts/check_precommit_violations.py
```

### Before Committing
```bash
# Scan your changes
python scripts/daily_violation_scan.py

# Check compliance
python scripts/check_precommit_violations.py

# Commit normally
git commit -m "your message"
# Hooks run automatically
```

### If You Hit An Error
```bash
# DON'T do this:
SKIP=check-credential-defaults git commit  # ❌ Will fail

# DO this:
# 1. Read the error message
# 2. Fix the code
# 3. Commit again
git commit -m "your fixed message"
```

### If Hook Is Wrong
```bash
# Contact the team:
# 1. Describe the legitimate use case
# 2. We'll review if hook needs adjustment
# 3. We update .pre-commit-config.yaml together
# (Don't bypass unilaterally)
```

---

## For DevOps / Platform Team

### Enable Daily Scanning
The workflow is already defined. Just ensure:

```bash
# File: .github/workflows/daily-violation-scan.yml
on:
  push:
    branches: [main, develop]   # Enabled ✓
  schedule:
    - cron: '0 9 * * *'         # Daily at 9 AM ✓
```

### Connect to Monitoring
Export metrics to your dashboard:

```bash
# Generate JSON for Grafana, DataDog, etc.
python scripts/violation_dashboard.py --json-export > metrics.json

# Schedule this daily:
0 10 * * * cd /repo && python scripts/violation_dashboard.py --json-export > /var/log/violations.json
```

### Email Alerts (Optional)
```bash
# When violations are found, email team
# Requires SMTP config, then:
python scripts/violation_dashboard.py --email-alert
```

---

## Success Metrics

You'll know enforcement is working when:

- ✅ Zero `SKIP=` commits to main in the last 30 days
- ✅ Daily violation scan reports "NO VIOLATIONS FOUND"
- ✅ All critical financial paths pass type checking
- ✅ No code review comments about "silent failures"
- ✅ Zero production incidents from missing data

---

## Questions?

**"Can I disable this check?"**  
No. These checks prevent financial data corruption. They are non-negotiable.

**"What if the check is wrong?"**  
Contact the team with a specific example. We review and update together.

**"Can I skip just one hook?"**  
No. Critical hooks cannot be skipped. This is by design.

**"Why is this so strict?"**  
Because silent failures in financial calculations can lose money, not just break code.

---

*Last updated: 2026-06-29*  
*Enforcement level: MAXIMUM*  
*Override level: NONE*
