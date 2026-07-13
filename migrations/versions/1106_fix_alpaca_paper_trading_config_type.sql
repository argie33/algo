-- Migration 1106: Ensure algo_config.alpaca_paper_trading has correct value/type
--
-- CONTEXT: Same class of bug as migration 1105 (swing_weight_* stored with wrong
-- value_type). AlgoConfig.get()'s type-check path (config/main.py, ~line 1869-1891)
-- only falls back to the DEFAULTS dict when the stored value is completely absent
-- (self._config.get(key) is None). If a row exists but its value_type doesn't match
-- VALIDATION_SCHEMA's expected type ("bool" for alpaca_paper_trading), _check_type()
-- fails, and get() returns the *function's* default parameter (unset -> None) instead
-- of ever consulting DEFAULTS - even though DEFAULTS has a correct value.
--
-- Confirmed live in AWS via CloudWatch: config.get("alpaca_paper_trading") returns
-- None on every orchestrator run (multiple independent Lambda cold starts, ruling out
-- a warm-container caching issue), crashing Phase 9 (reconciliation) at
-- AlpacaSyncManager.__init__ with "[ALPACA_SYNC] Config missing 'alpaca_paper_trading'"
-- even though algo/infrastructure/config/main.py's DEFAULTS dict has
-- ("true", "bool", "Use Alpaca paper account", "Execution Mode") and the local dev
-- database has this row correctly as ('true', 'bool'). Root cause unconfirmed without
-- direct AWS RDS access (not available to this session's IAM role), but the type-check
-- bypass is the only code path that produces this exact symptom, and it's the same
-- fix pattern already confirmed correct for migration 1105.
--
-- This deployment is paper trading only (Alpaca paper API keys, paper-api.alpaca.markets
-- base URL, ALPACA_PAPER_TRADING=true throughout terraform.tfvars) - 'true' is the
-- correct, safe value regardless of what's currently stored.

INSERT INTO algo_config (key, value, value_type, description)
VALUES ('alpaca_paper_trading', 'true', 'bool', 'Use Alpaca paper account')
ON CONFLICT (key) DO UPDATE SET
    value = 'true',
    value_type = 'bool'
WHERE algo_config.value_type != 'bool' OR algo_config.value IS DISTINCT FROM 'true';
