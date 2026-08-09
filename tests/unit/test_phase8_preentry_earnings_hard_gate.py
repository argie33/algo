"""Regression test: EARNINGS_IN_0-3D must be a standalone hard gate in PreEntryHealthValidator.

Before this fix, PreEntryHealthValidator.validate() only rejected a candidate if 2+ of its
4 health checks failed. That let earnings-imminent entries through whenever earnings proximity
was the ONLY failing check (RS/sector/market all clean) - real trade data from 2026-08-07 showed
this exact pattern: 14 of 20 trades were entered with earnings 0-1 days away and forced to
flatten within 1-2 days by position_monitor's earnings-blackout exit, for a net realized loss.
Earnings proximity alone must now block entry regardless of the other three checks.
"""

from unittest.mock import patch

from algo.orchestrator.phase8_preentry_health_check import PreEntryHealthValidator

_MODULE = "algo.orchestrator.phase8_preentry_health_check"


def _patch_checks(rs_weak=False, sector_weak=False, earnings_soon=False, market_stress=False):
    return (
        patch(f"{_MODULE}._check_rs_weakening", return_value=rs_weak),
        patch(f"{_MODULE}._check_sector_weak", return_value=sector_weak),
        patch(f"{_MODULE}._check_earnings_in_3d", return_value=earnings_soon),
        patch(f"{_MODULE}._check_market_distribution_stress", return_value=market_stress),
    )


def test_earnings_alone_blocks_entry_even_with_all_other_checks_clean():
    patches = _patch_checks(earnings_soon=True)
    with patches[0], patches[1], patches[2], patches[3]:
        passes, failed = PreEntryHealthValidator.validate("AAPL", "2026-08-07")

    assert passes is False
    assert failed == ["EARNINGS_IN_0-3D"]


def test_single_non_earnings_failure_still_passes():
    patches = _patch_checks(rs_weak=True)
    with patches[0], patches[1], patches[2], patches[3]:
        passes, failed = PreEntryHealthValidator.validate("AAPL", "2026-08-07")

    assert passes is True
    assert failed == ["RS_WEAKENING"]


def test_no_failures_passes():
    patches = _patch_checks()
    with patches[0], patches[1], patches[2], patches[3]:
        passes, failed = PreEntryHealthValidator.validate("AAPL", "2026-08-07")

    assert passes is True
    assert failed == []


def test_two_non_earnings_failures_still_blocks_via_existing_vote_rule():
    patches = _patch_checks(rs_weak=True, sector_weak=True)
    with patches[0], patches[1], patches[2], patches[3]:
        passes, failed = PreEntryHealthValidator.validate("AAPL", "2026-08-07")

    assert passes is False
    assert failed == ["RS_WEAKENING", "SECTOR_WEAK"]
