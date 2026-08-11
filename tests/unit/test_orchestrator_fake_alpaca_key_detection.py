"""Regression test: Orchestrator's startup fake-Alpaca-credential guard (blocks 'auto' mode
from trading with an obviously-placeholder key) must actually catch the exact example
credential its own comment names and this dev DB's algo_config.alpaca_api_key currently
holds - "PK0123456789ABCDEF".

BUG FOUND 2026-08-11: the original inline check required an exact `len(api_key) == 20`, but
"PK0123456789ABCDEF" is 18 characters. That length mismatch meant the documented example
silently passed the strict, RuntimeError-raising guard and only triggered a separate,
non-blocking WARNING-level check elsewhere in orchestrator.py - defeating the stated "fail
here at startup instead of later during trading" purpose for the exact credential the check
was written to catch, and leaving zero prior test coverage to catch the mismatch.

Extracted the check into a standalone is_obviously_fake_alpaca_key() so it's testable without
constructing a full Orchestrator (which needs DB/config/CredentialManager wiring).

Verified via: python -m pytest tests/unit/test_orchestrator_fake_alpaca_key_detection.py -v
"""

from algo.orchestration.orchestrator import is_obviously_fake_alpaca_key


def test_documented_placeholder_example_is_detected():
    """The exact value named in the guard's own comment, and currently live in this dev
    DB's algo_config.alpaca_api_key, must be caught."""
    assert is_obviously_fake_alpaca_key("PK0123456789ABCDEF") is True


def test_sequential_placeholder_detected_regardless_of_length():
    assert is_obviously_fake_alpaca_key("PK01234567") is True  # 10 chars, still sequential
    assert is_obviously_fake_alpaca_key("PK0123456789ABCDEF0123456789ABCDEF") is True  # long


def test_realistic_random_key_not_flagged():
    """A real, randomly-generated Alpaca key ID must NOT be flagged - the false-positive
    direction would block legitimate real-money trading at startup."""
    assert is_obviously_fake_alpaca_key("PKX7QM2NF9WZLR4KDT8B") is False
    assert is_obviously_fake_alpaca_key("PKAB19XZ44QLMN0293HJ") is False


def test_non_pk_prefix_not_flagged():
    assert is_obviously_fake_alpaca_key("AK0123456789ABCDEF") is False


def test_short_or_empty_key_not_flagged():
    assert is_obviously_fake_alpaca_key("PK") is False
    assert is_obviously_fake_alpaca_key("") is False
    assert is_obviously_fake_alpaca_key(None) is False


def test_non_alnum_suffix_not_flagged():
    assert is_obviously_fake_alpaca_key("PK0123-4567$ABCDEF") is False
