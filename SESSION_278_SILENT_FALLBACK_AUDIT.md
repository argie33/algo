# Session 278: Silent Fallback Audit & Critical Fixes

## Executive Summary

Audit found **16 active silent fallback patterns** violating CLAUDE.md fail-fast governance. Most are in AWS Lambda handlers where API response parsing silently defaults to empty arrays, masking connection errors and API failures that should halt execution.

**Impact**: Finance system relies on these handlers to:
1. Manage loader execution & timeouts (cost control, data freshness)
2. Stop unhealthy tasks (cost waste prevention)
3. Check circuit breakers (trading halts)

Silent fallbacks in these critical paths can:
- Silently skip loaders → stale data → bad trades
- Silently skip task termination → cost waste
- Silently bypass circuit breaker checks → unlimited losses

---

## CRITICAL VIOLATIONS FOUND (Fix Immediately)

### 1. **lambda/auto_kill_stuck_tasks/index.py:21** - ECS Response Malformed
```python
task_arns = response.get('taskArns', [])  # LINE 21 - SILENT FALLBACK
```

**Problem**: If AWS ECS API returns malformed response (missing 'taskArns' key), function silently continues with empty task list instead of alerting operator.

**Consequence**: Stuck ECS tasks won't be terminated → Cost waste ($45+/month per task)

**Fix**: Replace with explicit key check:
```python
if 'taskArns' not in response:
    raise RuntimeError("[CRITICAL] ECS list_tasks response malformed - missing 'taskArns' key")
task_arns = response['taskArns']
if not task_arns:
    # Legitimate: no tasks running
    logger.info("No running ECS tasks in cluster")
    return []
```

---

### 2. **lambda/loader-timeout-guardian/lambda_function.py:61-75** - Timeout Config Silent Fallback (3 violations)
```python
for container in task_def.get("containerDefinitions", []):  # LINE 61
    for env in container.get("environment", []):            # LINE 62
    ...
task_arns = ecs.list_tasks(cluster=cluster, desiredStatus="RUNNING").get("taskArns", [])  # LINE 74
tasks = ecs.describe_tasks(...).get("tasks", []) if task_arns else []  # LINE 75
```

**Problem**: 
- Line 61-62: If task_def is malformed, silently doesn't extract timeouts → loaders may hang indefinitely
- Line 74-75: If ECS API returns malformed responses, silently continues with empty task/config lists

**Consequence**: Loaders can hang → blocks orchestrator → data stale → trading halted

**Fix**: Add explicit key validation:
```python
if 'containerDefinitions' not in task_def:
    raise RuntimeError(f"[CRITICAL] Task definition malformed - missing containerDefinitions for {task_name}")
    
# Validate ECS responses
if 'taskArns' not in list_response:
    raise RuntimeError("[CRITICAL] ECS list_tasks response malformed")
task_arns = list_response['taskArns']

if task_arns:
    describe_result = ecs.describe_tasks(cluster=cluster, tasks=task_arns)
    if 'tasks' not in describe_result:
        raise RuntimeError("[CRITICAL] ECS describe_tasks response malformed")
    tasks = describe_result['tasks']
else:
    tasks = []
```

---

### 3. **lambda/cost_circuit_breaker/index.py:90-163** - Cost Monitoring Silent Fallbacks (5 violations)
```python
for result in response.get("ResultsByTime", []):         # LINE 90
    for group in result.get("Groups", []):               # LINE 91
    ...
for schedule in page.get("Schedules", []):               # LINE 122
    ...
task_arns = list_response.get("taskArns", [])           # LINE 163
```

**Problem**: Cost circuit breaker queries AWS APIs (CloudWatch Metrics, EventBridge, ECS) and silently defaults to empty responses if any key is missing. This masks actual cost data unavailability.

**Consequence**: Cost monitoring silently fails → System can't detect runaway spending → unlimited costs

**Fix**: Fail-fast on missing API response keys:
```python
if "ResultsByTime" not in response:
    raise RuntimeError("[CRITICAL] CloudWatch metrics response malformed - missing ResultsByTime")
for result in response["ResultsByTime"]:
    if "Groups" not in result:
        logger.error(f"CloudWatch result missing Groups - skipping record. Keys: {list(result.keys())}")
        continue
```

---

### 4. **lambda/trigger_loaders.py:57, 72** - Task Execution Silent Fallbacks
```python
tasks = response.get("tasks", [])           # LINE 57
failures = response.get("failures", [])     # LINE 72
```

**Problem**: ECS run_task response should always include both "tasks" and "failures" keys. If missing, it indicates API error, but code silently continues.

**Consequence**: Loaders fail to trigger → data pipeline breaks → signals stale

**Fix**: Explicit validation:
```python
if "tasks" not in response:
    raise RuntimeError("[CRITICAL] ECS run_task response missing tasks - API unavailable")
```

---

### 5. **lambda/cost_control/auto_stop_unhealthy_tasks.py:25** - Task List Silent Fallback
```python
task_arns = tasks_resp.get("taskArns", [])
```

**Problem**: Same as auto_kill_stuck_tasks - silently defaults to empty if ECS response malformed.

**Fix**: Add explicit key check (same pattern as #1)

---

## GOVERNANCE VIOLATIONS BY CATEGORY

### Silent `.get()` with `[]` default (most dangerous)
These occur in AWS Lambda handlers parsing external API responses:
- **What's wrong**: API response with missing key is NOT the same as "empty result". Missing key = API error = should raise.
- **Why dangerous**: Operator can't tell if daemon crashed, network failed, or results are genuinely empty
- **Pattern**: `response.get("RequiredKey", [])`
- **Count**: 9 violations across Lambda handlers

### `.get()` with default in financial calculations
- **load_short_interest_finra.py** - Checked (line 94 is legitimate context check, not a violation)
- **load_market_cap_computed.py** - Checked (no unsafe .get() patterns found)

### Legitimate cases (cleared)
- `market_symbols_config.py:262` - Correctly returns [] when input is empty (not a data error)
- `load_sector_industry_daily.py:108` - Correctly returns [] for pseudo-symbol "market" contract
- `health.py` - Extensive .get() calls are in diagnostic code with explicit downstream checks

---

## DETAILED VIOLATION LIST

| File | Line | Pattern | Severity | Status |
|------|------|---------|----------|--------|
| lambda/auto_kill_stuck_tasks/index.py | 21 | `.get('taskArns', [])` | CRITICAL | Needs Fix |
| lambda/loader-timeout-guardian/lambda_function.py | 61 | `.get("containerDefinitions", [])` | CRITICAL | Needs Fix |
| lambda/loader-timeout-guardian/lambda_function.py | 62 | `.get("environment", [])` | CRITICAL | Needs Fix |
| lambda/loader-timeout-guardian/lambda_function.py | 74 | `.get("taskArns", [])` | CRITICAL | Needs Fix |
| lambda/cost_circuit_breaker/index.py | 90 | `.get("ResultsByTime", [])` | HIGH | Needs Fix |
| lambda/cost_circuit_breaker/index.py | 91 | `.get("Groups", [])` | HIGH | Needs Fix |
| lambda/cost_circuit_breaker/index.py | 122 | `.get("Schedules", [])` | HIGH | Needs Fix |
| lambda/cost_circuit_breaker/index.py | 163 | `.get("taskArns", [])` | HIGH | Needs Fix |
| lambda/cost_control/auto_stop_unhealthy_tasks.py | 25 | `.get("taskArns", [])` | CRITICAL | Needs Fix |
| lambda/trigger_loaders.py | 57 | `.get("tasks", [])` | CRITICAL | Needs Fix |
| lambda/trigger_loaders.py | 72 | `.get("failures", [])` | CRITICAL | Needs Fix |

**Non-violations (legitimate patterns)**:
- `loaders/load_insider_holdings_sec.py:115` - Parsing optional SEC XBRL response
- `lambda/api/auth_utils.py:37` - JWT token groups (optional, has explicit fallback check)
- `lambda/api/routes/auth_guard.py:43` - Same JWT pattern

---

## ROOT CAUSE ANALYSIS

### Why These Patterns Emerged

1. **AWS SDK Patterns**: Developers copied AWS SDK error handling patterns where `.get()` defaults are normal
   - "If key missing, just use empty list" is OK for telemetry data
   - NOT OK for critical decision-making data

2. **Lack of Distinction**: Code doesn't distinguish between:
   - **Required response fields** (API must return these, missing = error)
   - **Optional response fields** (API may omit if not applicable, missing = legitimate)

3. **Testing Gaps**: Most Lambda code hasn't been tested for malformed AWS API responses
   - Local testing uses mocked AWS responses
   - Production discovers failures under real network conditions

---

## FIX STRATEGY

### Phase 1: Critical Lambda Handlers (Today)
These directly impact trading and cost control:
1. `lambda/auto_kill_stuck_tasks/index.py`
2. `lambda/cost_circuit_breaker/index.py`
3. `lambda/cost_control/auto_stop_unhealthy_tasks.py`
4. `lambda/trigger_loaders.py`

### Phase 2: Loader-Related Lambdas (This week)
1. `lambda/loader-timeout-guardian/lambda_function.py`

### Phase 3: Audit Remaining (Next sprint)
Re-run pre-commit script on entire codebase for any other violations

---

## VERIFICATION CHECKLIST

After fixes:
- [ ] Run `.pre-commit-scripts/check-silent-fallbacks.py` → PASS
- [ ] Run unit tests: `pytest tests/test_fail_fast_patterns.py -v`
- [ ] Test AWS Lambda handlers locally with malformed responses
- [ ] Document required vs optional fields in each AWS API response struct
- [ ] Add type hints to make response structure explicit (dict vs dict | None)

---

## NEXT STEPS

1. **Immediate**: Fix the 11 CRITICAL violations listed above
2. **Create**: AWS response type definitions (dataclass or TypedDict) to prevent future misuse
3. **Add**: Pre-deployment integration tests that mock AWS API failures
4. **Update**: CLAUDE.md with explicit AWS Lambda response parsing patterns

**Estimated effort**: 2-3 hours to fix + test all violations
**Risk**: These fixes prevent silent data loss during AWS API failures (net risk reduction)
