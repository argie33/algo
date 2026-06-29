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
- **See**: FALLBACK_AUDIT_COMPLETE.md for fixed patterns

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
- **See**: PHASE3_LOADERS_AUDIT.md for patterns

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
