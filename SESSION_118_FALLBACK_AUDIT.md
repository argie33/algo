# Session 118: Comprehensive Fallback Anti-Pattern Audit

## Goal
Identify and eliminate ALL silent fallback patterns in financial app where explicit fail-fast is mandatory.

## Critical Issues Found

### TIER 1 - SYSTEMIC (Affects entire orchestrator flow)

1. **orchestrator.py:162** - Configuration fallback
   ```python
   is_paper_trading = self.config.get("alpaca_paper_trading", False)
   ```
   **Issue**: If key missing, silently defaults to False (live trading). Reverses the safe default.
   **Fix**: Use explicit None check + raise

2. **orchestrator.py:204-210** - Credential fallback
   ```python
   except RuntimeError as e:
       if "Secrets Manager access failed" in str(e):
           logger.warning("...Falling back to paper mode.")
   ```
   **Issue**: AWS credential failure triggers silent mode switch. Operator unaware of security degradation.
   **Fix**: Remove fallback, raise instead

3. **orchestrator.py:1348** - Phase results fallback
   ```python
   executor_result.get("results", {})
   ```
   **Issue**: Missing phase execution results return empty dict. Indistinguishable from "no results to process".
   **Fix**: Raise on missing, never silently return empty

### TIER 2 - CRITICAL TRADING PATHS

4. **phase8_entry_execution.py:172** - Entry strategy fallback
   ```python
   if not symbols_with_precomputed:
       return {}
   ```
   **Issue**: Returns empty dict when "no entries allowed". Caller can't distinguish from "0 entries computed".
   **Fix**: Return explicit PhaseResult with "skipped" or "halted" status

5. **phase1_data_freshness.py:139** - Data validation fallback
   ```python
   return None
   ```
   **Issue**: Returns None to signal "data is fresh". Implicit success signal.
   **Fix**: Return explicit PhaseResult with "ok" status

6. **phase_executor.py:171** - Dependency validation fallback
   ```python
   return None  # Validation passed
   ```
   **Issue**: Returns None to signal "all dependencies ok". Implicit success signal.
   **Fix**: Return boolean or raise exception

### TIER 3 - FINANCIAL DATA EXTRACTION

7. **order_manager.py:362** - Order status
   ```python
   status = data.get("status")
   if status is None:
       raise ValueError(...)  # GOOD - has guard
   ```
   **Status**: ALREADY FIXED

8. **executor.py:442** - Order result status
   ```python
   order_status = order_result.get("status")
   ```
   **Issue**: No guard. If status missing, proceeds with None.
   **Fix**: Add None check + raise

9. **exit_engine.py:653** - Exit signal fallback
   ```python
   new_stop = exit_signal.get("new_stop")
   ```
   **Issue**: Returns None if missing. Used without guard in subsequent trades.
   **Fix**: Add None check + raise before use

10. **exit_strategies.py:235,283,385** - Decision extraction
    ```python
    new_stop=decision.get("new_stop")
    ```
    **Issue**: Extracts from decision dict without checking if present.
    **Fix**: Validate before using

### TIER 4 - NOTIFICATIONS & REPORTING

11. **notifications.py:72** - Entry price
    ```python
    entry_price = details.get("entry_price")
    ```
    **Issue**: No guard. Silent None if missing.
    **Fix**: Add guard

12. **notifications.py:128** - Exit price
    ```python
    exit_price = details.get("exit_price")
    ```
    **Issue**: No guard. Incomplete notifications sent.
    **Fix**: Add guard

13. **notifications.py:196** - Event status
    ```python
    status = event.get("status")
    ```
    **Issue**: No guard.
    **Fix**: Add guard

### TIER 5 - DASHBOARD SILENT RETURNS

14-38. **25 dashboard files** with `return []`, `return {}`, `return None`, `return False`
- dashboard.py, local_api_server.py, fetchers_portfolio.py, watch/manager.py, etc.
- **Issue**: Return empty/None without explicit markers
- **Fix**: Return PhaseResult or data_unavailable marker structures

### TIER 6 - CONFIG FALLBACKS

39. **position_sizer.py:175** - Execution mode
    ```python
    execution_mode = self.config.get("execution_mode", "paper")
    ```
    **Issue**: Silent paper default if key missing. Critical trading mode decision.
    **Fix**: Remove default, raise on missing

40. **exit_engine.py:171,177,182** - Config fallbacks
    ```python
    max_hold_val = self.config.get("max_hold_days")
    eight_wk_val = self.config.get("eight_week_rule_threshold_pct")
    eight_wk_window_val = self.config.get("eight_week_rule_window_days")
    ```
    **Issue**: Returns None if keys missing. Used without guards.
    **Fix**: Add validation at startup

## Pattern Summary

| Pattern | Count | Severity | Root Cause |
|---------|-------|----------|-----------|
| `.get()` on financial data | 40+ | HIGH | Implicit None returns |
| `or` fallback chains | 2691 | MIXED | Silent defaults |
| Silent empty returns | 21+ | CRITICAL | Implicit success markers |
| Configuration fallbacks | 10+ | CRITICAL | Missing keys assume safe defaults |
| Try/except suppression | 15+ | HIGH | Swallow errors without markers |

## Fix Strategy (Priority Order)

**Phase A (TODAY)**: Orchestrator systemic fixes - ✅ COMPLETE
- [x] orchestrator.py:162 - Remove alpaca_paper_trading fallback
- [x] orchestrator.py:204-210 - Remove credential fallback (raise on auth failure)
- [x] orchestrator.py:1357 - Remove results dict fallback (raise on missing)
- [x] buy_signal_generator.py - Fix truthy checks (use `is None`)
- [x] position_sizer.py - Remove Alpaca exception swallowing (raise instead)
- [x] phase7_signal_generation.py - Remove neutral 50.0 risk score default
- [x] portfolio_manager.py - Make paper mode fallback explicit (with better logging)
- [x] fetchers_portfolio.py - Replace truthy check with `is None`

**Phase B (IMMEDIATE)**: High priority fixes - ✅ COMPLETE
- [x] reconciliation.py - Remove hardcoded initial_capital default
- [x] fetchers_signals.py - Upgrade timeout handling (explicit unavailability)
- [x] load_economic_data.py - Require FRED API key (raise instead of empty string)

**Phase C (NEXT)**: Remaining fallback patterns
- [ ] order_manager - Verify all status checks (some already correct)
- [ ] exit_engine - Verify config .get() calls
- [ ] exit_strategies - Verify decision extraction
- [ ] executor - Verify order_status access

**Phase D (FINAL)**: Notifications & dashboard
- [ ] notifications.py - Guard all price/status extraction
- [ ] daily_report.py - Guard report extraction
- [ ] Dashboard files - Convert 25 silent return patterns

## Testing Strategy

1. **Config missing tests** - Verify exceptions raised, not silent fallbacks
2. **Data missing tests** - Verify raises or explicit markers, never silent None
3. **Integration tests** - Verify orchestrator fails-fast on any data unavailable
4. **Regression tests** - Verify all 9 phases execute correctly with explicit status

## Success Criteria

✅ Zero implicit status signals (None/empty dict used to signal success/failure)
✅ Zero `.get()` with default fallbacks on financial data
✅ Zero silent try/except suppressors on trading paths
✅ All exceptions propagate with clear error messages
✅ Pre-commit hook passes with no violations

