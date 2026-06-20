# Codebase Governance

## QUICK START

AWS credential error? Run: `scripts/refresh-aws-credentials.ps1`

For system architecture and config, see `steering/system.md`.

## STEERING RULES

1. **Content:** System map, procedures, architecture, troubleshooting. NO live status, timestamps, or incident logs.
2. **Clarity:** Complete sentences. Spell out times (4:00 AM ET).
3. **Procedures:** Document "how to debug X" with verifiable steps, never "X is broken" (stale status).
4. **Updates:** Code changes + steering updates in same commit. No async updates.

## Where Information Goes

| What | Where | Why |
|------|-------|-----|
| System design, procedures, config | `steering/system.md` | Single source of truth |
| Current state, errors happening now | GitHub Actions logs, AWS console | Real-time |
| What happened and why | `git log` with good commit messages | Permanent record |

**NEVER in steering:** Live status, timestamps, incident logs, "as of", blockers.

## Code Cleanliness (Pre-Commit Enforced)

**Blocks commits:**
- `.env` files (use AWS Secrets Manager)
- `pdb`, `ipdb`, `breakpoint()` left in code
- `print()` statements in library code (use logging)
- Files > 1MB (binaries, artifacts)

**Allowed:**
- `print()` in: `algo_loader_*.py`, `algo_daily_report.py`, `scripts/`, `tests/`

**Type checking & imports (enforced):**
- Type errors from mypy BLOCK commits
- Code must be importable (no NameError)
- Before committing: `python -m mypy <file>.py --ignore-missing-imports`

## Documentation Lifecycle

**Steering docs** (`steering/system.md`): PERMANENT only.
- ✅ Architecture, procedures, thresholds, troubleshooting
- ❌ Status, incident logs, "completed/fixed" with dates

**Memory files** (`.claude/projects/*/memory/*.md`): Actionable NOW or delete.
- ✅ Ongoing feedback, current context, references
- ❌ Historical incidents, completed fixes (they're in git log)

**Rule:** After a fix ships → delete the memory file. Git log is the record.

## Security Baseline

- NO `.env` files. Ever.
- Credentials: AWS Secrets Manager (production), PowerShell profile (local)
- CI: GitHub Secrets for deploy tokens only
- Rotate quarterly (first Monday), immediately if leaked
- Auditable: All secrets in Secrets Manager, never in code or config files

See `steering/system.md` → **Credentials & Secrets** for procedures.

## Dashboard API Validation Strategy

**Problem:** API responses can drift from expected schema. Old approach: Dashboard panels use 775+ `.get()` calls with None defaults, silently masking missing fields and showing placeholder data.

**Solution:** Fail-fast strategy at all layers prevents schema drift and hidden failures.

**Three-Layer Architecture:**

1. **API Boundary** (`api_data_layer.py:api_call()`): All API calls validated before returning
   - Implements retry logic with exponential backoff
   - Circuit breaker pattern prevents hammering downed APIs
   - Caches responses for fallback during outages
   - On failure: returns `{"_error": "message"}` only

2. **Endpoint Validators** (`response_validators.py`): 15+ validators for critical endpoints
   - Portfolio, Performance, Positions, Trades, Signals
   - Markets, Last-Run, Risk Metrics, Config
   - Health, Circuit Breakers, Sector Rotation
   - On validation failure: returns `{"_error": "message"}` to halt processing

3. **Fetchers** (`fetchers.py`): Enforce fail-fast, NO fallback dictionaries
   - Check `_is_api_error(data)` → return error dict immediately, no placeholder fields
   - Validate critical fields (e.g., Markets requires SPY & VIX)
   - On stale data (>freshness threshold) → return `{"_error": "...", "_data_stale": True}`
   - On missing required fields → return `{"_error": "..."}` 
   - On exception → return `{"_error": "..."}` (never {"_error": "...", field1: None, field2: None, ...})

**Key Rule:** Fetchers return ONLY `{"_error": "message"}` on failure, NO fallback structures with None values. This surfaces data issues immediately in the error panel.

**Critical Endpoints (Must Never Be None):**
- Portfolio: `total_portfolio_value`, `total_cash`, `position_count`
- Performance: `total_trades`, `winning_trades`, `losing_trades`
- Markets: `spy_close`, `vix_level` (both required for position sizing)
- Last-Run: `run_id`, `success`

**When Adding New Endpoints:**
1. Update `shared_contracts/dashboard_api_contract.py` with schema
2. Add validator in `tools/dashboard/response_validators.py`
3. Register endpoint path in `VALIDATORS` mapping
4. In fetchers.py: validate critical fields BEFORE returning success
5. Return only `{"_error": "..."}` if validation fails (no fallback fields)
6. Document which fields are critical (must never be None)

**Panel Best Practices:**
- Always check `error_boundary.has_error(data)` first (returns True if `_error` set)
- If error: display `error_boundary.error_summary_panel()` to user
- Only access fields if no error (validation guaranteed they exist)
- Use direct access for critical fields: `data["field_name"]`
- Use `.get()` only for truly optional fields
