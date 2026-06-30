# Codebase Governance (Quick Reference)

**Steering docs in `steering/`:**
- `GOVERNANCE.md` — Architecture, safety rules, system map
- `OPERATIONS.md` — CI/CD, hotload config, circuit breaker monitoring, troubleshooting
- `DATA_LOADERS.md` — Loader pipeline, parallelism tuning, freshness thresholds
- `LINT_POLICY.md` — Type safety, linting enforcement

**Start here:** GOVERNANCE.md + OPERATIONS.md cover 80% of needs.

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

Return explicit `data_unavailable: True` markers instead of `None` for optional data (sentiment, quality metrics, etc.). See `GOVERNANCE.md` "Data Quality" section for full rules.

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

## Common Tasks → Quick Reference

| Task | See |
|------|-----|
| Understand system map | GOVERNANCE.md (system architecture section) |
| Add new trading rule | GOVERNANCE.md (trading safety), then OPERATIONS.md (hotload config) |
| Fix data loader bug | DATA_LOADERS.md (loader model), OPERATIONS.md (troubleshooting) |
| Debug test failures | OPERATIONS.md (CI/CD pipeline), LINT_POLICY.md (enforcement) |
| Investigate stale data | DATA_LOADERS.md (freshness thresholds), OPERATIONS.md (diagnostics) |
| Emergency halt trading | OPERATIONS.md (circuit breaker override) |
| Rotate credentials | AWS credential refresh: `scripts/refresh-aws-credentials.ps1` |
