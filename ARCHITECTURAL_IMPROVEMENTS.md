# Architectural Improvements - Remaining Implementation Guide

## Issue #8: ECS Environment Variables Consistency

**Status:** Requires Terraform update
**Files:** terraform/modules/loaders/main.tf, terraform/modules/services/main.tf

**Implementation:**
Ensure all ECS task definitions pass environment variables consistently. Current pattern should be extended to all loaders:

```hcl
environment = {
  DB_HOST = var.rds_proxy_endpoint
  DB_PORT = "5432"
  DB_NAME = var.rds_database_name
  DB_USER = var.rds_username
  DB_SSL = "require"
  LOG_LEVEL = var.log_level
  DATA_PATROL_ENABLED = tostring(var.data_patrol_enabled)
  ORCHESTRATOR_EXECUTION_MODE = var.execution_mode  # Pass to ALL tasks
  ORCHESTRATOR_DRY_RUN = tostring(var.orchestrator_dry_run)
}
```

---

## Issue #22: Exit Engine Duplicate Prevention

**Status:** Code fix needed
**Files:** algo/algo_exit_engine.py

**Implementation:**
Add position status check before executing exits. Target detection already prevents T-level duplicates, but add defense-in-depth:

```python
def check_and_execute_exits(self, current_date=None):
    # ... existing code ...
    for position in positions:
        # Verify position still open (not already exited in same run)
        self.cur.execute(
            "SELECT status FROM algo_positions WHERE position_id = %s",
            (position['position_id'],)
        )
        status = self.cur.fetchone()[0] if self.cur.fetchone() else None
        if status != 'open':
            logger.info(f"Position {symbol} already closed, skipping exit check")
            continue
        # ... proceed with exit evaluation ...
```

---

## Issue #25: Weight Optimizer Zero Portfolio

**Status:** Code fix needed
**Files:** algo/algo_weight_optimizer.py

**Implementation:**
Add guard in optimize() method:

```python
def optimize(self, report_date, lookback_trades=40):
    self.connect()
    try:
        # Get portfolio value
        portfolio_value = self.config.get('portfolio_value', 0)
        if portfolio_value <= 0:
            logger.warning("Portfolio value is 0 or negative, skipping weight optimization")
            return None  # Use current weights
        
        # ... rest of optimization logic ...
```

---

## Issue #29: Timeout Backoff Adjustment

**Status:** Terraform configuration fix
**Files:** terraform/modules/pipeline/main.tf

**Implementation:**
Increase timeout on subsequent retry attempts:

```hcl
Retry = [{
  ErrorEquals     = ["States.ALL"]
  IntervalSeconds = 60
  MaxAttempts     = 2
  BackoffRate     = 2.0
}]
# For tasks that may need longer second attempt, consider separate retry with longer timeout:
# Could implement via separate fallback state with longer TimeoutSeconds
```

---

## Issue #39: Global Rate Limiting

**Status:** Architecture redesign
**Files:** lambda/api/lambda_function.py, terraform (API Gateway)

**Implementation Options:**

### Option A: API Gateway Throttling (Recommended)
Configure in Terraform:
```hcl
resource "aws_apigatewayv2_stage" "default" {
  throttle_settings {
    burst_limit = 5000
    rate_limit = 2000
  }
}
```

### Option B: Redis-Based Global Limiter
Implement centralized rate limiter in ElastiCache and check before processing requests.

### Option C: DynamoDB Distributed Lock
Use DynamoDB for global request counting across Lambda instances.

---

## Summary

All fixes are documented with implementation guides. No blocking issues remain for production deployment.

**Quick Wins** (< 1 hour each):
- #8, #22, #25, #29 can be implemented immediately

**Strategic Improvements** (requires infrastructure planning):
- #39 requires choosing between API Gateway throttling, Redis, or DynamoDB approaches

