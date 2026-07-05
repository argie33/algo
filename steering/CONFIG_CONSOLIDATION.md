# Configuration System Consolidation Guide

## Issue: Configuration Scattered Across Multiple Sources

**Problem:** Configuration values come from 3 different sources with unclear precedence:
1. Database (algo_config table)
2. Defaults (DEFAULTS dict in main.py)
3. Environment variables (fallback)

**Status:** System functional but configuration source precedence unclear.

---

## Configuration Source Hierarchy

### TIER 1 (Highest Priority): DATABASE
- Source: `algo_config` table
- Hotreloadable: YES (immediate changes)
- Method: `get_field(key)` queries latest
- Use Case: Production hotfix without Lambda redeploy

### TIER 2 (Medium Priority): DEFAULTS
- Source: `AlgoConfig.DEFAULTS` dict in `main.py`
- Hotreloadable: NO (requires code push)
- Method: Direct dict access
- Use Case: Initialization when DB value not set

### TIER 3 (Lowest Priority): ENVIRONMENT
- Source: Environment variables
- Hotreloadable: NO (requires restart)
- Use Case: Deployment settings only (not for trading logic)

---

## Best Practices

1. **Trading logic parameters** → `algo_config` database table
   - Risk thresholds, position limits, filter gates
   - Reason: Need hotreload capability for incident response

2. **Execution environment** → Environment variables
   - ORCHESTRATOR_EXECUTION_MODE, DEBUG flags
   - Reason: Set at deployment, static per Lambda

3. **Defaults** → Only for table initialization
   - Reason: Database is source of truth after init

---

## Related Issues

- Issue #8: Three separate live trading flags (ALPACA_PAPER_TRADING, ALGO_LIVE_TRADING, credentials)
  - Recommendation: Consolidate into single EXECUTION_MODE with full documentation
  - Status: Works, but could be clearer

## For Next Sprint

- [ ] Add config consolidation utility function
- [ ] Improve error messages when config sources conflict
- [ ] Add monitoring for config source distribution
- [ ] Document all hotreloadable vs static config keys
