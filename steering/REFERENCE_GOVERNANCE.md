# Reference: Detailed Governance Patterns

This file contains detailed governance information not needed in every conversation. Linked from `GOVERNANCE.md`.

---

## Exception Handling (Detailed)

All exceptions inherit from `AlgoError` (see `algo/exceptions.py`).

- `DataLoadError`: Failed to fetch data from database/API/files. Set `retry_eligible=True` for network, `False` for schema
- `ValidationError`: Field missing, type error, or business logic violation
- `ConfigError`: Configuration key missing/invalid (never recoverable)
- `CircuitBreakerError`: Too many failures — automatic retry waits for recovery
- `PortfolioError`: Portfolio/cash/position inconsistency
- `PositionError`: Position-specific trading error

**Error responses in APIs:** Return `{"_error": "message"}` only on failure. Never mix error dict with fallback fields. Client checks `has_error(data)` before accessing fields.

---

## Validation & Fail-Fast (Detailed)

**At boundaries (once):** Validate all inbound data (API responses, database data, configuration).

**Inside code:** Assume valid. No defensive wrapping. Let exceptions propagate.

**Two-tier validation:**
- **Lambda outbound:** `ResponseValidator` from `shared_contracts/response_validator.py` (generic schema-based)
- **Dashboard inbound:** Specialized validators in `tools/dashboard/response_validators.py` (fail-fast, 15+ endpoint-specific)

DO NOT use one validator type in the other's context.

---

## Data Loader Patterns (Detailed)

**Three-tier criticality:**
1. **CRITICAL** (VIX, portfolio value, prices): Fail-fast, no stale cache. Use `DataImportance.CRITICAL`
2. **REQUIRED** (financials, technical): Fail cleanly. Use `DataImportance.REQUIRED`
3. **OPTIONAL** (put/call, yield curve): Return None on failure. Use `DataImportance.OPTIONAL`

All use canonical `CircuitBreaker` from `utils.infrastructure.circuit_breaker`.

---

## Circuit Breaker Patterns (Detailed)

**Problem:** Loaders handled API outages inconsistently — some failed fast, some used stale cache silently (up to 9 days old).

**Solution:** Three-tier criticality model with canonical `CircuitBreaker` from `utils.infrastructure.circuit_breaker`.

### Tier 1: CRITICAL (Fail-Fast, No Cache)
- **Examples:** VIX level, portfolio value, SPY price, market close data
- **Behavior:** Retry with exponential backoff (2s, 4s, 8s, 16s, 32s). Fail immediately after 3 failures.
- **Code:** `DataImportance.CRITICAL`
- **Failure:** Raises RuntimeError / phase fails / orchestrator retries later
- **NEVER:** Silently use stale cache

### Tier 2: REQUIRED (Fail with Context)
- **Examples:** Financial statements, technical indicators, market breadth
- **Behavior:** Retry exponentially. Fail cleanly if exhausted.
- **Code:** `DataImportance.REQUIRED`
- **Failure:** Raises RuntimeError / phase can skip or retry
- **NEVER:** Continue computation without this data

### Tier 3: OPTIONAL (Graceful Degradation)
- **Examples:** Put/call ratio, yield curve slope, sector rotation
- **Behavior:** Short timeout (no full retry loop). On failure: log warning, return None.
- **Code:** `DataImportance.OPTIONAL`
- **Failure:** Returns `None` / downstream checks for None and skips enrichment
- **NEVER:** Silently fill with stale value

**For Each Loader:**
1. Identify criticality of each data source
2. Create breaker: `CircuitBreaker(name="...", importance=DataImportance.X)`
3. Wrap fetches: `breaker.execute(fetch_func=lambda: ...)`
4. Document criticality in docstring
5. For OPTIONAL: Check `if vix is not None` before using

**Testing:** (1) Cut network / loader fails <30s (not timeout). (2) API returns 503 / retry 3x then fail (no cache). (3) Verify logs show "CIRCUIT OPEN" or graceful degradation messages.

**Monitoring:** CloudWatch alerts on CIRCUIT OPEN for CRITICAL/REQUIRED data (immediate escalation). Logs show state transitions: `CLOSED / OPEN / HALF_OPEN / CLOSED`.

**Migration:**
- Phase 1 (2026-06-27): VIX, prices, portfolio value (CRITICAL)
- Phase 2 (2026-07-04): Financial statements, technical indicators (REQUIRED)
- Phase 3 (2026-07-11): Put/call, yield curve, sector rotation (OPTIONAL)

---

## Database Transactions & Atomicity

**Multi-Step Operations:** All operations affecting trades and positions must be atomic:
- Entry: Trade entry + position creation + audit log all commit together or rollback together
- Exit: Trade status update + position quantity update + stop price adjustment + audit log are atomic
- Reconciliation: Alpaca sync + position status updates + profit/loss calculation are atomic

**Row-Level Locking:** Multi-step updates use `FOR UPDATE` to lock rows and prevent concurrent modifications during transaction. Example: executor.py locks both algo_trades and algo_positions rows before executing partial exits.

**Rowcount Verification:** After each critical UPDATE, verify `cursor.rowcount == 1` (exactly one row updated). Mismatch indicates lost update or concurrency violation — transaction rolls back.

**Connection Context:** All database operations use `DatabaseContext` which auto-commits on success and rollbacks on any exception. Never manually commit or close connections.

**Savepoints in Error Handling:** Loaders use named savepoints for recoverable errors. On failure, rollback to savepoint (not full transaction) and continue with next record. On critical error, exception propagates and full rollback occurs.

---

## GitHub Actions Workflows

**Production Auto (4):** deploy-all-infrastructure.yml, deploy-staging.yml, ci-fast-gates.yml, build-push-ecr.yml

**Scheduled (3):** run-fred-loader.yml (5 AM ET), rotate-credentials.yml (quarterly, first Monday), verify-both-envs.yml (6h)

**Infrastructure (2):** build-lambda-layer.yml, verify-and-init-db.yml (manual dispatch)

**Credentials (4):** rotate-credentials.yml (primary quarterly), rotate-credentials-simple.yml (fallback), update-credentials.yml (API key sync), check-credential-status.yml (audit). Local: `scripts/refresh-aws-credentials.ps1`.

**Manual (3):** manual-invoke-loaders.yml, manual-invoke-orchestrator.yml, test-and-debug.yml

**Test (1):** reset-cognito-test-user.yml

---

## Troubleshooting Guide

**AWS credential error:** `scripts/refresh-aws-credentials.ps1`

**Lambda 502 (VPC cold-start):** Provisioned concurrency should prevent. Check: `aws lambda get-provisioned-concurrency-config --function-name algo-api-dev`. Retry with backoff.

**Lambda 5xx:** Check logs: `aws logs tail /aws/lambda/algo-api-dev --follow`. Verify RDS Proxy reachable (security groups), Lambda layer deployed (psycopg2).

**Phase 1 halts (stale data):** Check DATA_FRESHNESS_MAX_HOURS in algo_config, morning prep (`scripts/orchestrator-history.py recent 1`), and yfinance CloudWatch logs for rate limiting.

**RDS connections saturated:** Check CloudWatch DatabaseConnections (expect <30 morning, 20-30 EOD). Slow queries: RDS Performance Insights. Reduce parallelism: `scripts/update-loader-parallelism.py`.

**Orchestrator lock timeout:** Check: `aws ecs list-tasks --cluster algo-cluster` (no stuck tasks). Check CloudWatch for "Lock acquisition failed".

**Market regime halts entries:** Phase 5 halts when market_exposure_daily sets `is_entry_allowed=false` (triggers: 6+ heavy-volume down days in 25 sessions, VIX > 40 with rising trend, SPY below 30-week MA, HY spread > 8.5%). Check: `SELECT date, is_entry_allowed, halt_reasons FROM market_exposure_daily WHERE date = CURRENT_DATE ORDER BY date DESC LIMIT 1`. Entries resume automatically when conditions improve (designed risk control).

**Missing scheduled orchestrator runs:** If <4 daily runs, check AWS EventBridge Scheduler console:
- `algo-algo-schedule-morning-dev` (9:30 AM ET) / ENABLED
- `algo-algo-schedule-afternoon-dev` (1:00 PM ET) / ENABLED
- `algo-algo-schedule-preclose-dev` (3:00 PM ET) / ENABLED
- `algo-algo-schedule-dev` (5:30 PM ET) / ENABLED

If disabled: `cd terraform/ && terraform apply -var-file=terraform.tfvars`. Verify Lambda permissions: EventBridge Scheduler must have `lambda:InvokeFunction` on `algo-orchestrator-dev`.

---

## Key Files Reference

- `algo/algo_orchestrator.py` — 7-phase orchestrator
- `lambda/api/lambda_function.py` — REST API
- `terraform/main.tf` — infrastructure as code
- `lambda/db-init/schema.sql` — database schema
- `loaders/load_*.py` — data loaders
- `tools/dashboard/` — terminal dashboard
- `run-dashboard.ps1` — convenience wrapper
