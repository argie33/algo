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

**Problem:** API responses can drift from expected schema. Dashboard panels use 775+ `.get()` calls that default to None, masking missing fields.

**Solution:** Fail-fast validation at API boundary prevents schema drift from reaching dashboard UI.

**Architecture:**
1. **API Boundary** (`api_data_layer.py:api_call()`): All API calls validated before returning to fetchers
2. **Endpoint Validators** (`response_validators.py`): 15+ validators for critical endpoints
   - Portfolio, Performance, Positions, Trades, Signals
   - Markets, Last-Run, Risk Metrics, Config
   - Health, Circuit Breakers, Sector Rotation
3. **Error Propagation:** Validation errors returned as `{"_error": "..."}` 
4. **Fetchers** (`fetchers.py`): Check `_error` before processing; return error dicts on validation failure

**Critical Endpoints (Must Never Be None):**
- Portfolio: `total_portfolio_value`, `total_cash`, `position_count`
- Performance: `total_trades`, `winning_trades`, `losing_trades`
- Markets: `spy_close`, `vix_level`
- Last-Run: `run_id`, `success`

**When Adding New Endpoints:**
1. Update `shared_contracts/dashboard_api_contract.py` with schema
2. Add validator in `tools/dashboard/response_validators.py`
3. Register endpoint path in `VALIDATORS` mapping
4. Document which fields are critical (must never be None)

**Panel Best Practices:**
- After `_error_panel()` check, trust data structure (validation passed)
- Use `.get()` for optional fields only
- Use direct access for critical fields: `data["field_name"]`
- If field can legitimately be None, use: `data.get("field_name")`
