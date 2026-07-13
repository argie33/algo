# Trading Mode Configuration Guide

## Overview

The system supports multiple execution modes to allow testing, development, and production trading.

**All trading-mode configuration MUST be explicit in the `algo_config` table. Never use silent fallbacks.**

---

## Configuration Keys

### Primary: `execution_mode`
**Database Key:** `execution_mode`  
**Valid Values:** `"paper"`, `"dry"`, `"review"`, `"auto"`  
**Default (if missing):** NONE - **FAILS FAST with RuntimeError**  
**Location in Code:** `algo/infrastructure/config/execution_config.py:get_execution_mode()`

| Mode | Description | Live Broker | Database | Use Case |
|------|-------------|------------|----------|----------|
| `paper` | Paper trading account | No | Yes | Development/testing without risk |
| `dry` | Dry-run (no trades executed) | No | Yes | Test orchestrator without any trades |
| `review` | Review mode (manual approval) | No | Yes | Sandbox trading with review step |
| `auto` | Auto-execute trades | Yes | Yes | Production trading with live account |

### Secondary: `alpaca_paper_trading`
**Database Key:** `alpaca_paper_trading`  
**Valid Values:** `"true"` or `"false"`  
**Type:** Boolean  
**Default (if missing):** NONE - **FAILS FAST with RuntimeError**  
**Location in Code:** `algo/infrastructure/config/execution_config.py:is_paper_trading()`

**Purpose:** Explicitly specifies Alpaca account type (paper vs live).

**Important Notes:**
- Must ALWAYS be explicitly set, even if redundant with `execution_mode`
- Paper mode (`true`) allows graceful degradation if broker credentials missing
- Live mode (`false`) requires valid Alpaca credentials in AWS Secrets Manager

---

## Configuration Validation

### At Startup (Orchestrator Init)
**Location:** `algo/orchestration/orchestrator.py:__init__` (line 162)
```python
is_paper_trading = self.config.get("alpaca_paper_trading")
if is_paper_trading is None:
    raise RuntimeError(
        "[STARTUP] CRITICAL: alpaca_paper_trading key must be explicitly set in algo_config. "
        "Never assume defaults for trading mode. Set to True for paper trading, False for live."
    )
```

### At Phase Execution
All phases that execute trades validate `alpaca_paper_trading`:
- **Phase 6 (Exit Execution):** Validates before exit operations
- **Phase 8 (Entry Execution):** Validates before trade execution
- **Reconciliation (Phase 9):** Validates during portfolio reconciliation

Each phase will fail-fast with clear error if key missing.

---

## Recommended Configuration Setup

### For Development/Testing
```sql
UPDATE algo_config SET value = 'paper' WHERE key = 'execution_mode';
UPDATE algo_config SET value = 'true' WHERE key = 'alpaca_paper_trading';
```

### For Production
```sql
UPDATE algo_config SET value = 'auto' WHERE key = 'execution_mode';
UPDATE algo_config SET value = 'false' WHERE key = 'alpaca_paper_trading';
-- ALSO: Ensure Alpaca credentials in AWS Secrets Manager under 'algo/alpaca'
```

### For Sandbox
```sql
UPDATE algo_config SET value = 'review' WHERE key = 'execution_mode';
UPDATE algo_config SET value = 'true' WHERE key = 'alpaca_paper_trading';
```

---

## Common Issues & Troubleshooting

### Error: "alpaca_paper_trading config key missing"
**Cause:** The `algo_config` table row for `alpaca_paper_trading` is missing or NULL.

**Fix:**
```sql
-- Check if row exists
SELECT * FROM algo_config WHERE key = 'alpaca_paper_trading';

-- If missing, insert it
INSERT INTO algo_config (key, value, value_type, description)
VALUES ('alpaca_paper_trading', 'true', 'bool', 'Use Alpaca paper account')
ON CONFLICT (key) DO UPDATE SET value = 'true';
```

### Error: "execution_mode config key missing"
**Cause:** The `algo_config` table row for `execution_mode` is missing or NULL.

**Fix:**
```sql
-- Check if row exists
SELECT * FROM algo_config WHERE key = 'execution_mode';

-- If missing, insert it
INSERT INTO algo_config (key, value, value_type, description)
VALUES ('execution_mode', 'paper', 'string', 'Trade execution mode (paper|dry|review|auto)')
ON CONFLICT (key) DO UPDATE SET value = 'paper';
```

### Error: "Invalid execution_mode '[value]'"
**Cause:** The value in `algo_config` is not one of the valid modes.

**Fix:**
```sql
-- Valid values are: 'paper', 'dry', 'review', 'auto'
UPDATE algo_config SET value = 'paper' WHERE key = 'execution_mode';
```

---

## Architecture: Why Explicit Configuration?

### Problem Solved
**Session [Current]:** Found modules using conflicting defaults:
- `reconciliation.py` defaulted `alpaca_paper_trading` to **True**
- `alpaca_sync_manager.py` defaulted it to **False**
- `phase6/phase8` defaulted it to **False**

This created non-deterministic behavior: the trading mode depended on which code path ran first!

### Solution
All code now requires explicit configuration:
- **No `.get()` with defaults** on trading-mode keys
- **Fail-fast** if key missing: clear error message with recovery steps
- **Single source of truth:** `algo_config` table + defaults in `AlgoConfig.DEFAULTS`

### Benefits
1. **Predictability:** Trading mode is always known and explicit
2. **Safety:** Impossible to accidentally slip into wrong trading mode
3. **Auditability:** Every trading decision is tied to explicit config at time of execution
4. **Clarity:** Error messages tell exactly what's misconfigured and how to fix it

---

## Code Pattern

### ✅ CORRECT: Require Explicit Configuration
```python
if "alpaca_paper_trading" not in config:
    raise ValueError(
        "[MODULE] Config missing 'alpaca_paper_trading'. "
        "Trading mode must be explicit (paper vs live). "
        "Check algo_config table has this key."
    )
is_paper_trading = config["alpaca_paper_trading"]
```

### ❌ WRONG: Silent Fallback
```python
is_paper_trading = config.get("alpaca_paper_trading", False)  # Bad!
```

### ✅ CORRECT: Use ExecutionConfig Helper (Recommended)
```python
from algo.infrastructure.config import ExecutionConfig

# If you have AlgoConfig instance:
exec_config = ExecutionConfig(algo_config_instance)
is_paper = exec_config.is_paper_trading()  # Properly validates and fails-fast
```

---

## Related Resources

- **ExecutionConfig:** `algo/infrastructure/config/execution_config.py`
  - Methods: `get_execution_mode()`, `is_paper_trading()`, `get_max_trades_per_day()`, etc.
  - All methods validate explicitly and fail-fast

- **AlgoConfig:** `algo/infrastructure/config/main.py`
  - Main config manager with database backend
  - Hotreloadable from `algo_config` table

- **Validation Schema:** `algo/config_schema.py`
  - Schema definition for all config keys
  - Type validation and constraints

- **Tests:** `tests/integration/test_execution_config.py`
  - Tests for execution mode validation

