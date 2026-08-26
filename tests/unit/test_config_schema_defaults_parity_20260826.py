"""Regression test: AlgoConfig.DEFAULTS and config_schema.VALIDATION_SCHEMA must stay in sync.

[[config_three_tier_governance_gap_20260824]]: a new algo_config key must be registered in
three separate places (VALIDATION_SCHEMA, DEFAULTS, and a migration seed row), and missing
DEFAULTS specifically is silent - VALIDATION_SCHEMA's own fail-closed value papers over the
gap at runtime, so nothing actually breaks, it's just an admin-panel metadata hole that was
previously only ever caught by manually reading monitor_data_staleness.py's startup console
warning. This test makes that warning a hard CI failure instead of an opt-in observation.

Does not cover the third tier (migration seed rows) - that would need a real migrated
database, which this repo's unit suite deliberately never spins up (see tests/conftest.py's
fully-mocked DB fixtures). VALIDATION_SCHEMA's own fail-closed value already covers a missing
migration seed row for a fresh environment, which is why that tier is lower-severity.
"""

from algo.infrastructure.config.main import AlgoConfig
from algo.infrastructure.config_schema import VALIDATION_SCHEMA


def test_every_validation_schema_key_has_a_defaults_entry() -> None:
    missing = sorted(set(VALIDATION_SCHEMA) - set(AlgoConfig.DEFAULTS))
    assert not missing, (
        f"Key(s) in VALIDATION_SCHEMA but missing from AlgoConfig.DEFAULTS: {missing}. "
        "Add a DEFAULTS entry (value, type, description, category) for each."
    )


def test_every_defaults_key_is_declared_in_validation_schema() -> None:
    extra = sorted(set(AlgoConfig.DEFAULTS) - set(VALIDATION_SCHEMA))
    assert not extra, (
        f"Key(s) in AlgoConfig.DEFAULTS but missing from VALIDATION_SCHEMA: {extra}. "
        "Every DEFAULTS key must have a matching VALIDATION_SCHEMA validation rule."
    )


def test_shared_keys_declare_matching_type() -> None:
    """Catch e.g. DEFAULTS saying "int" while VALIDATION_SCHEMA says "float" for the same key -
    a real historical bug class in this file (migrations/versions/1106_fix_alpaca_paper_trading_config_type.sql
    exists specifically because a type mismatch like this shipped once already)."""
    mismatches = []
    for key in sorted(set(VALIDATION_SCHEMA) & set(AlgoConfig.DEFAULTS)):
        schema_type = VALIDATION_SCHEMA[key][0]
        defaults_type = AlgoConfig.DEFAULTS[key][1]
        if schema_type != defaults_type:
            mismatches.append(f"{key}: schema={schema_type!r} vs defaults={defaults_type!r}")
    assert not mismatches, "Type mismatch between VALIDATION_SCHEMA and DEFAULTS:\n" + "\n".join(mismatches)
