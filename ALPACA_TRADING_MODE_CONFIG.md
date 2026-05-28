# Alpaca Trading Mode Runtime Configuration

**Issue:** #20 (COMPREHENSIVE_ISSUES.md)  
**Status:** 🟡 DESIGNED  
**Date:** 2026-05-28

---

## Overview

This document describes how to make Alpaca trading mode (paper vs. live) configurable at runtime without requiring Terraform redeploy.

---

## Current Implementation (Limitation)

**File:** `terraform/terraform.tfvars`

```hcl
alpaca_paper_trading = true  # Hardcoded, requires redeploy to change
```

**Problem:**
- To switch paper → live, must edit tfvars and run `terraform apply`
- Deploy time: ~20 minutes (unacceptable during market hours)
- Can't toggle between environments dynamically
- No audit trail of mode changes

---

## Proposed Solution: RDS Configuration Table

### 1. Configuration Table Schema

**Table:** `algo_runtime_config`

```sql
CREATE TABLE algo_runtime_config (
    config_key VARCHAR(100) PRIMARY KEY,
    config_value VARCHAR(255) NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    
    UNIQUE(config_key)
);

-- Initial data
INSERT INTO algo_runtime_config VALUES
    ('alpaca_trading_mode', 'paper', 'paper | live | disabled', now(), 'system'),
    ('max_position_size', '5000', 'Max dollars per position', now(), 'system'),
    ('circuit_breaker_vix_threshold', '50', 'VIX level to trigger halt', now(), 'system'),
    ('data_freshness_sla_hours', '24', 'Max age before Phase 1 halt', now(), 'system');
```

### 2. Loading at Orchestrator Cold-Start

**File:** `algo/config/runtime_config.py` (NEW)

```python
class RuntimeConfig:
    _cache = {}
    _cache_timestamp = None
    CACHE_TTL = 300  # 5 minutes
    
    @classmethod
    def get(cls, key, default=None):
        """Load config from RDS with 5-min cache."""
        now = time.time()
        
        # Return cached if still valid
        if cls._cache_timestamp and (now - cls._cache_timestamp) < cls.CACHE_TTL:
            return cls._cache.get(key, default)
        
        # Refresh cache from RDS
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT config_key, config_value FROM algo_runtime_config"
                )
                cls._cache = {row[0]: row[1] for row in cur.fetchall()}
                cls._cache_timestamp = now
        except Exception as e:
            logger.error(f"Failed to load runtime config: {e}")
            # Return default if load fails
            return default
        
        return cls._cache.get(key, default)


# Usage in orchestrator
alpaca_mode = RuntimeConfig.get('alpaca_trading_mode', 'paper')
if alpaca_mode == 'live':
    execution_mode = 'live'
elif alpaca_mode == 'paper':
    execution_mode = 'paper'
else:
    execution_mode = 'disabled'
```

### 3. Management API Endpoint

**Endpoint:** `POST /api/admin/config/{key}`

```python
@app.route('/api/admin/config/<config_key>', methods=['POST'])
@require_admin_auth
def update_config(config_key):
    """Update runtime configuration."""
    data = request.get_json()
    new_value = data.get('value')
    
    # Validate key
    ALLOWED_KEYS = ['alpaca_trading_mode', 'max_position_size', ...]
    if config_key not in ALLOWED_KEYS:
        return error_response(400, 'invalid_config_key', f'Key {config_key} not allowed')
    
    # Validate value format
    if config_key == 'alpaca_trading_mode':
        if new_value not in ('paper', 'live', 'disabled'):
            return error_response(400, 'invalid_value', 'Must be paper, live, or disabled')
    
    # Update in RDS
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE algo_runtime_config 
                   SET config_value = %s, 
                       updated_at = NOW(),
                       updated_by = %s
                   WHERE config_key = %s""",
                (new_value, current_user_id(), config_key)
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        return error_response(500, 'update_failed', str(e))
    
    # Log audit trail
    logger.info(f"CONFIG CHANGE: {config_key} = {new_value} (by {current_user_id()})")
    
    return json_response(200, {
        'config_key': config_key,
        'config_value': new_value,
        'updated_at': datetime.now().isoformat(),
        'updated_by': current_user_id()
    })
```

### 4. CLI for Quick Toggling

**Script:** `scripts/toggle-alpaca-mode.sh`

```bash
#!/bin/bash
# Toggle Alpaca trading mode between paper and live

TARGET_MODE=${1:-paper}  # Default: paper
REGION=${AWS_REGION:-us-east-1}

if [[ ! "$TARGET_MODE" =~ ^(paper|live|disabled)$ ]]; then
    echo "Usage: toggle-alpaca-mode.sh {paper|live|disabled}"
    exit 1
fi

echo "Switching Alpaca trading mode to: $TARGET_MODE"

# Call API endpoint
curl -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $(get_auth_token)" \
    -d "{\"value\": \"$TARGET_MODE\"}" \
    https://api.example.com/api/admin/config/alpaca_trading_mode

echo "✓ Mode switched to $TARGET_MODE"
```

---

## Implementation Phases

### Phase 1: Table + Read API (1-2 weeks)

1. Create `algo_runtime_config` table via migration
2. Add `RuntimeConfig` class to read from RDS with caching
3. Update orchestrator to use `RuntimeConfig.get('alpaca_trading_mode')`
4. Test with manual RDS updates

### Phase 2: Write API (1 week)

1. Add `POST /api/admin/config/<key>` endpoint
2. Implement validation for each config key
3. Add admin-only auth requirement
4. Test mode switching without redeploy

### Phase 3: Monitoring (1 week)

1. CloudWatch metrics for mode changes
2. Audit log entries for each change
3. Dashboard showing current mode
4. Alert on unexpected mode switches

---

## Usage Examples

### Switch to Live Trading (Manual)

```bash
# Before market open
./scripts/toggle-alpaca-mode.sh live

# Verify
psql algo -c "SELECT config_value FROM algo_runtime_config WHERE config_key = 'alpaca_trading_mode';"
# Output: live
```

### Switch Back to Paper (Emergency)

```bash
# If issues during live trading
curl -X POST \
    -H "Authorization: Bearer $AUTH_TOKEN" \
    -d '{"value": "paper"}' \
    https://api.example.com/api/admin/config/alpaca_trading_mode

# Takes effect at next orchestrator run (within 5 min)
```

### Check Current Mode

```bash
# Via API
curl https://api.example.com/api/admin/config/alpaca_trading_mode \
    -H "Authorization: Bearer $AUTH_TOKEN"

# Response: 
# {
#   "alpaca_trading_mode": "live",
#   "updated_at": "2026-05-28T14:30:00Z",
#   "updated_by": "admin@example.com"
# }
```

---

## Safety Features

### 1. Cache TTL (5 minutes)

- Read from RDS only every 5 minutes
- Avoids excessive database queries
- Accounts for network latency in config propagation

### 2. Validation

- Only allow `paper`, `live`, or `disabled` values
- Require admin authentication to change
- Log all changes to audit log

### 3. Fallback

- If RDS query fails, use cached value
- If no cache, use environment variable default
- Never crash orchestrator due to config read failure

### 4. Audit Trail

```sql
-- View config change history
SELECT 
    config_key, 
    config_value, 
    updated_at, 
    updated_by 
FROM algo_runtime_config
WHERE config_key = 'alpaca_trading_mode'
ORDER BY updated_at DESC;
```

---

## Monitoring & Alerting

### CloudWatch Metrics

```python
# Log every config read
logger.info(f"Config: alpaca_trading_mode = {alpaca_mode}", extra={
    'MetricName': 'AlpacaTradingMode',
    'MetricValue': 1 if alpaca_mode == 'live' else 0
})

# Alert if switched to live unexpectedly
if alpaca_mode == 'live' and was_paper_before:
    sns.publish(
        TopicArn=ALERT_TOPIC,
        Subject="ALERT: Alpaca Trading Mode Changed to LIVE",
        Message=f"Mode switched at {now()}. Check permissions."
    )
```

### Dashboard Widget

```json
{
  "type": "metric",
  "properties": {
    "metrics": [
      ["Custom", "AlpacaTradingMode"]
    ],
    "period": 300,
    "stat": "Average",
    "region": "us-east-1",
    "title": "Alpaca Trading Mode (0=paper, 1=live)"
  }
}
```

---

## Current Status

**What's Working:**
- Terraform variable for initial setup ✓
- Environment variable fallback ✓

**What Needs Implementation:**
- `algo_runtime_config` table ✗
- `RuntimeConfig` class ✗
- Management API endpoint ✗
- CLI script ✗
- Monitoring/alerting ✗

---

## Design Decisions

1. **Cache 5 minutes:** Balance between freshness and DB load
2. **RDS vs. Secrets Manager:** Secrets Manager for credentials only; config in RDS for flexibility
3. **Admin-only auth:** Prevent accidental trading mode changes
4. **Fallback chain:** TF var → env var → RDS → default (safety)

---

## Testing Plan

```bash
# 1. Test cache behavior
time python -c "from algo.config.runtime_config import RuntimeConfig; 
  for i in range(3): print(f'{i}: {RuntimeConfig.get(\"alpaca_trading_mode\")}')"

# 2. Test mode switch effects
curl -X POST -d '{"value": "live"}' .../config/alpaca_trading_mode
sleep 5  # Wait for cache TTL
# Orchestrator should now use live mode

# 3. Test audit trail
SELECT * FROM algo_runtime_config WHERE config_key = 'alpaca_trading_mode';
```

---

**Summary:** Alpaca trading mode can be made runtime-configurable via `algo_runtime_config` RDS table + management API. Deferred to Phase 2 (full implementation) but design is complete and ready for implementation.
