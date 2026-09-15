-- Migration 1295: Seed intraday_prior_day_drop_halt_pct into algo_config
--
-- ISSUE (real-money-readiness audit, 2026-09-15): this key has been a required entry in
-- algo/infrastructure/config/config_defaults_risk.py (and config_schema.py's bounds table)
-- since it was added, but was never seeded into the algo_config table itself. Live-confirmed:
-- instantiating AlgoConfig prints "[AlgoConfig] ALERT: 1 critical thresholds NOT loaded from
-- database (using defaults/fail-closed): ['intraday_prior_day_drop_halt_pct']" on every
-- process start. The code already fails closed/safe (falls back to the -2.0% code default,
-- see circuit_breaker_market_conditions.py), so this was never a live safety gap - but it
-- meant the threshold couldn't be tuned from algo_config like every other risk knob without a
-- code change, and the ALERT fired on every single startup.
--
-- -2.0 default: matches the existing code default in config_defaults_risk.py exactly, so
-- seeding this row is a no-op for current behavior - it only makes the threshold operator-
-- tunable going forward and silences the spurious startup ALERT.

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('intraday_prior_day_drop_halt_pct', '-2.0', 'float',
        'Prior-day SPY drop % that halts new entries (must be negative)',
        'migration-1295')
ON CONFLICT (key) DO NOTHING;
