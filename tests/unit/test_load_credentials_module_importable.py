"""Regression test for the 2026-07-27 cleanup sweep (commit f6d061869) that deleted
scripts/load_credentials.py along with 85 other "one-off diagnostic scripts" - but
scripts/run_local_orchestrator.py (the tool CLAUDE.md and multiple test docstrings
document as the way to test the orchestrator locally) does
`from scripts.load_credentials import ensure_credentials_loaded` at module level.

That import is wrapped in try/except, so a missing module doesn't crash the tool - it
silently logs a warning and falls through to whatever Alpaca credentials happen to be
in the environment, which is exactly the kind of silently-degraded behavior this
project's rules exist to catch. No existing test imported this module, so its deletion
went unnoticed until manually traced from run_local_orchestrator.py's import list.
"""

import scripts.load_credentials as load_credentials


def test_ensure_credentials_loaded_exists():
    assert hasattr(load_credentials, "ensure_credentials_loaded")
    assert callable(load_credentials.ensure_credentials_loaded)


def test_load_credentials_from_database_exists():
    assert hasattr(load_credentials, "load_credentials_from_database")
    assert callable(load_credentials.load_credentials_from_database)
