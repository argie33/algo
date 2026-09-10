"""Regression test: _is_sec_rate_limit_error must not false-match company_info_sec's own
BACKFILL_DAYS config-validation error message.

FIXED 2026-09-07: the classifier used to check the bare substring "rate limit", which matched
the phrase "Full backfills risk excessive load times and API rate limits" inside that
ValueError's own text - a static warning unrelated to any real SEC EDGAR throttling. This
mislabeled a real config bug as "SEC rate limiting", triggering a silent 2-failure graceful
skip (SEC loaders skip after just 2 consecutive failures) that cascaded to "valuations" and its
dependents, silently preventing a code-only ratio-computation fix from ever taking effect in the
DB. Live-reproduced during the LLY/RIGL tax-benefit-inflated-PE fix verification session.
"""

from scripts.local_loader_scheduler import _is_sec_rate_limit_error

BACKFILL_DAYS_CONFIG_ERROR = (
    "local_loader_scheduler: subprocess exited with code 1. Full log: "
    "C:\\Users\\arger\\code\\algo\\logs\\load_company_info_sec_1788790486.log. Last output:\n"
    "2026-09-07 09:14:47,397 - ERROR - [COMPANY_INFO FATAL] Loader crashed: ValueError: "
    "[CONFIG] BACKFILL_DAYS=3650 exceeds configured maximum (1825 days). Full backfills risk "
    "excessive load times and API rate limits. Use incremental load (BACKFILL_DAYS=0) or "
    "smaller backfill window (max 1825 days). Override with LOADER_MAX_BACKFILL_DAYS "
    "environment variable."
)


def test_backfill_days_config_error_is_not_a_sec_issue():
    assert _is_sec_rate_limit_error(BACKFILL_DAYS_CONFIG_ERROR) is False


def test_genuine_sec_429_is_a_sec_issue():
    assert _is_sec_rate_limit_error("SEC EDGAR request failed: rate limited (429)") is True


def test_genuine_sec_edgar_mention_is_a_sec_issue():
    assert _is_sec_rate_limit_error("Connection to SEC EDGAR timed out after 3 retries") is True


def test_bare_429_is_a_sec_issue():
    assert _is_sec_rate_limit_error("HTTP 429 received from upstream") is True


def test_unrelated_error_is_not_a_sec_issue():
    assert _is_sec_rate_limit_error("KeyError: 'shares_outstanding'") is False
