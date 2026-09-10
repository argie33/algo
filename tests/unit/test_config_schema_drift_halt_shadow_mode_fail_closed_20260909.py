#!/usr/bin/env python3
"""Regression test for a backwards fail_closed_value found via the 2026-09-09
real-money-readiness audit.

VALIDATION_SCHEMA's own header comment defines the contract: "fail_closed_value: value to
use if admin tries to set an invalid value (prevents trading)". For
reconciliation_drift_halt_shadow_mode (True = observe-only/no halt, False = actually halt
on a confirmed sustained broker-vs-DB equity drift), the fail-closed value was True - the
PERMISSIVE direction, not the trading-preventing one. Currently inert in practice
(AlgoConfig.get()'s fail_closed_value branch only fires when is_critical is also True,
and this key is deliberately marked non-critical - see config_schema.py's own comment for
why), but a genuine latent landmine: if a corrupted/invalid DB value for this key were ever
read alongside is_critical=True, the system would silently fall back to NOT halting on a
confirmed critical drift, exactly backwards from the "prevents trading" contract every
other entry in this table follows correctly (e.g. base_risk_pct fails closed to a LOWER
risk value, halt_drawdown_pct fails closed to a MORE conservative threshold).
"""

from algo.infrastructure.config_schema import VALIDATION_SCHEMA


def test_drift_halt_shadow_mode_fail_closed_value_prevents_trading_not_permits_it():
    schema_type, min_val, max_val, is_critical, fail_closed_value = VALIDATION_SCHEMA[
        "reconciliation_drift_halt_shadow_mode"
    ]
    assert schema_type == "bool"
    # False (shadow mode OFF) means the halt actually fires - that's the direction that
    # "prevents trading" on a confirmed critical drift, matching this schema's own
    # documented fail-closed contract.
    assert fail_closed_value is False, (
        "fail_closed_value for a halt-gating shadow-mode flag must be the value that "
        "actually enforces the halt (False), not the value that silently disables it"
    )
