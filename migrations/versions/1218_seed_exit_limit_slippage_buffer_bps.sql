-- Migration 1218: Seed exit_limit_slippage_buffer_bps into algo_config
--
-- ISSUE: every algo-initiated exit (executor.py's _send_alpaca_exit) submitted an
-- unconditional market order with zero price protection, even for non-urgent exits
-- (profit targets, time-based exits, portfolio rotation, trailing-stop tightening) where
-- there is no reason to forfeit control of the fill price. Hard stop-loss exits
-- (exit_stage="stop", capital preservation, bypasses min_hold_days) correctly keep pure
-- market orders - certainty of exit outweighs price control there. For every other exit
-- reason, executor.py now submits a marketable limit order at
-- exit_price * (1 - exit_limit_slippage_buffer_bps / 10000), aggressive enough to fill like
-- a market order in normal conditions while capping worst-case slippage if price gaps.
--
-- 50 bps (0.5%) default: wide enough to clear typical spread + a few seconds of price drift
-- on the liquidity-screened universe (min_adv_shares/min_adv_dollars gates already exclude
-- illiquid names), narrow enough to meaningfully cap slippage vs. a naked market order.

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('exit_limit_slippage_buffer_bps', '50.0', 'float',
        'Marketable-limit buffer (bps below exit_price) for non-urgent exits; hard stop-loss exits always use pure market orders',
        'migration-1218')
ON CONFLICT (key) DO UPDATE
    SET value = '50.0',
        description = 'Marketable-limit buffer (bps below exit_price) for non-urgent exits; hard stop-loss exits always use pure market orders',
        updated_by = 'migration-1218',
        updated_at = CURRENT_TIMESTAMP;
