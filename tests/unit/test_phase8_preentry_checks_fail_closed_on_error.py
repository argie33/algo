"""Regression test: phase8_preentry_health_check.py's individual checks must fail CLOSED
(treat an error as "flag this candidate as risky") on any exception, not fail open.

Before this fix, all 4 checks (_check_rs_weakening, _check_sector_weak,
_check_earnings_in_3d, _check_market_distribution_stress) caught every exception -
including a transient DB connection blip - and returned False ("no problem found"),
identical to a genuine clean check. Unlike the earnings check (independently backstopped
by pretrade_checks.py's fail-closed EarningsBlackout re-check in the real order-placement
path - see [[phase8_preentry_fail_open_investigated_safe_20260809]]), RS weakening, sector
weakness, and market distribution stress have no other per-candidate hard-gate backstop
anywhere in the entry path (exposure_policy.py's tiers only affect position sizing, not
per-candidate rejection). A transient error could previously silently wave a genuinely
RS-weakening or distribution-stressed candidate through this specific check.

Each check is a soft signal (PreEntryHealthValidator.validate() passes with <=1 of 4
checks failed), so flagging on error doesn't reject a candidate by itself - it just stops
silently discarding the fact that something couldn't be verified.
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_preentry_health_check import (
    _check_earnings_in_3d,
    _check_market_distribution_stress,
    _check_rs_weakening,
    _check_sector_weak,
)

_MODULE = "algo.orchestrator.phase8_preentry_health_check"


def _raising_db_context():
    """A DatabaseContext mock whose __enter__ raises, simulating a transient DB error."""
    mock_ctx = MagicMock()
    mock_ctx.__enter__.side_effect = RuntimeError("connection reset by peer")
    mock_ctx.__exit__.return_value = False
    return mock_ctx


class TestPreEntryChecksFailClosedOnDbError:
    def test_rs_weakening_flags_on_db_error(self):
        with patch(f"{_MODULE}.DatabaseContext", return_value=_raising_db_context()):
            result = _check_rs_weakening("AAPL", "2026-08-07")
        assert result is True, "a DB error must be treated as 'RS weakening detected', not 'no problem'"

    def test_sector_weak_flags_on_db_error(self):
        with patch(f"{_MODULE}.DatabaseContext", return_value=_raising_db_context()):
            result = _check_sector_weak("AAPL", "2026-08-07")
        assert result is True, "a DB error must be treated as 'sector weak', not 'no problem'"

    def test_earnings_in_3d_flags_on_db_error(self):
        with patch(f"{_MODULE}.DatabaseContext", return_value=_raising_db_context()):
            result = _check_earnings_in_3d("AAPL", "2026-08-07")
        assert result is True, "a DB error must be treated as 'earnings imminent', not 'no problem'"

    def test_market_distribution_stress_flags_on_db_error(self):
        with patch(f"{_MODULE}.DatabaseContext", return_value=_raising_db_context()):
            result = _check_market_distribution_stress("2026-08-07")
        assert result is True, "a DB error must be treated as 'market under stress', not 'no problem'"
