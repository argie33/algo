-- Migration 1262: Seed absolute_max_dollars_per_trade into algo_config
--
-- ISSUE (real-money-readiness audit, 2026-09-06): position_sizer.py has an independent,
-- portfolio-value-agnostic fat-finger backstop (absolute_max_dollars_per_trade,
-- added 2026-08-31) specifically to catch a runaway order if portfolio_value were ever
-- wrong upstream - every OTHER cap in the sizer is a percentage of portfolio_value, so a
-- bad equity read would make every percentage check look "compliant" while authorizing an
-- arbitrarily large real-dollar trade. The check was deliberately left opt-in (skipped
-- entirely when unset) since the right ceiling depends on the account's real intended
-- size. It was never actually configured anywhere - dormant, providing zero protection.
--
-- $10,000 default: a conservative, account-size-agnostic ceiling safe for a small account
-- (comfortably above what max_position_size_pct=4.75% would size for an account in the
-- sub-$25k PDT-restricted range) while still being low enough to actually catch a gross
-- sizing error before it reaches the broker. Raise this in algo_config once real funding
-- size is known - it should track well above the largest position max_position_size_pct
-- would legitimately produce, not below it.

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('absolute_max_dollars_per_trade', '10000.0', 'float',
        'Hard per-trade dollar ceiling independent of portfolio_value - fat-finger backstop against a corrupted equity read. Raise once real account funding size is known.',
        'migration-1262')
ON CONFLICT (key) DO NOTHING;
