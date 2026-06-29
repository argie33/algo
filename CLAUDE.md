# Codebase Governance (Quick Reference)

See **`steering/GOVERNANCE.md`** for complete architecture, standards, and safety configuration.

See **`steering/OPERATIONS.md`** for CI/CD procedures, deployments, and troubleshooting.

See **`steering/LINT_POLICY.md`** for lint/code-quality discipline.

## Quick Start

**AWS credential error?** Run: `scripts/refresh-aws-credentials.ps1`

## Key Rules (Enforced Pre-Commit)

1. **No `.env` files** — Use AWS Secrets Manager
2. **No debug code** — `pdb`, `ipdb`, `breakpoint()`
3. **Type-safe code** — `mypy` must pass
4. **Code cleanliness** — Linting + formatting enforced
5. **NEVER set safety thresholds to zero** — Doing so bypasses all guards

**All other governance rules are in `steering/GOVERNANCE.md`.**

## Credential Handling (Fail-Fast, No Silent Fallbacks)

**Critical credentials** (passwords, API keys, secrets):
- ❌ **Never** use `.get()` with empty string defaults: `secret.get("password", "")`
- ✅ **Always** validate at load time with explicit errors:
  ```python
  secret_dict = json.loads(response["SecretString"])
  if "password" not in secret_dict:
      raise ValueError("[CRITICAL] Password missing from Secrets Manager")
  ```
- **Rationale**: Missing credentials silently default to empty strings → authentication bypassed. Must fail fast.
- **Status**: All credential validation patterns hardened across lambda, loaders, and API

## Optional Data Contracts (Explicit Unavailability Markers)

**Optional enrichment** (growth metrics, sentiment, quality data):
- ❌ **Never** return `None` without context: `if not data: return None`
- ✅ **Always** return explicit markers when data unavailable:
  ```python
  if not data:
      return {
          "symbol": symbol,
          "data_unavailable": True,
          "reason": "insufficient_price_history"
      }
  ```
- **Rationale**: Callers need to distinguish "no data available" from "error occurred". Explicit markers enable proper handling.
- **Pattern**: Optional loaders (AAII sentiment, stock scores, etc.) return dict with `data_unavailable` flag
- **Implementation**: All 20+ loaders use explicit unavailability markers instead of None returns

## Dashboard Data Access Pattern (Fail-Fast in UI Layer)

**Dashboard panels** (render UI elements and display data):
- ❌ **Never** use defensive `.get()` chains: `data.get("x", {}).get("y", 0)`
- ✅ **Always** use error_boundary pattern:
  ```python
  from dashboard.error_boundary import has_error
  from dashboard.panels.data_extractors import safe_extract, safe_get_dict, safe_get_list

  def render_panel(data):
      # 1. Check for error once at entry point
      if has_error(data):
          return error_panel(data)
      
      # 2. For critical fields, validate presence
      result = safe_extract(data, "total", "symbols", defaults={"symbols": []})
      total = result["total"]  # Guaranteed safe
      
      # 3. For optional fields, use safe accessors
      scores = safe_get_dict(data.get("scores"))  # Returns None if missing, raises if error
      if scores:
          display_scores(scores)
  ```
- **Rationale**: Dashboard error_boundary pattern (check error once → direct access → optional accessors) prevents defensive `.get()` chains that hide missing data visibility
- **Key Helpers**:
  - `safe_extract()`: Validates required fields present or use defaults
  - `safe_get_dict()`, `safe_get_list()`: For optional nested data (returns None if missing, raises if corrupted)
- **Pre-Commit Guard**: `check-dashboard-get-pattern.py` flags functions with 5+ `.get()` calls without `has_error()` check
- **Location**: `dashboard/panels/data_extractors.py` has complete pattern implementation

## Logging Discipline (Missing Data Visibility)

**Financial data** missing (HIGH priority):
- **ERROR/CRITICAL level** — Missing critical market data (yield curve, halts, circuit breaker data)
- **WARNING level** — Missing high-priority financial data (quality metrics, growth metrics, technical indicators)

**Optional enrichment** missing:
- **DEBUG level** — Missing optional enrichment (sentiment, industry ranking, positioning data)

**Rationale**: Missing CRITICAL/HIGH data must be visible to ops (WARNING/ERROR). Silent DEBUG logs hide degraded risk calculations. All patterns must be loggable (never silent).

## Production Readiness Checklist

Before deploying changes touching these areas:
- ✅ No new `.get()` fallbacks for passwords/API keys
- ✅ Optional data returns explicit `data_unavailable` markers
- ✅ Missing financial data logged at WARNING or ERROR (not DEBUG)
- ✅ All critical paths validated with `mypy strict`
- ✅ Pre-commit hooks pass (type safety, linting, format)
