"""Regression test for the 2026-08-25 fix to
algo/orchestrator/phase8_preentry_health_check.py::_check_sector_weak (see
[[sector_rotation_signal_orphaned_never_scheduled_fixed_20260825]] in memory).

_check_sector_weak had two independent bugs, either one alone sufficient to make it
permanently inert since it was written:
(1) It joined against company_profile to look up the candidate's own GICS sector and queried
    sector_rotation_signal WHERE sector = <that sector name>, but
    SectorRotationDetector._persist() has only ever written ONE row per date, hardcoded to
    the literal sector value "market_rotation" - a single market-wide signal, not a
    per-GICS-sector breakdown. A per-candidate sector name could never match that row.
(2) The value comparison checked signal.lower() in ("weak", "decline", "warning", "negative"),
    but _determine_rotation_signal() only ever returns "severe_defensive_rotation" /
    "defensive_rotation_warning" / "mild_defensive_lead" / "neutral" - none of which are in
    that set.

Fixed to query the real single "market_rotation" row and match its real vocabulary.
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_preentry_health_check import _check_sector_weak

_MODULE = "algo.orchestrator.phase8_preentry_health_check"


def _db_context_returning(row):
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = row
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


class TestSectorWeakChecksRealMarketRotationSignal:
    def test_severe_defensive_rotation_flags_weak(self):
        with patch(f"{_MODULE}.DatabaseContext", return_value=_db_context_returning(("severe_defensive_rotation",))):
            assert _check_sector_weak("AAPL", "2026-08-25") is True

    def test_defensive_rotation_warning_flags_weak(self):
        with patch(f"{_MODULE}.DatabaseContext", return_value=_db_context_returning(("defensive_rotation_warning",))):
            assert _check_sector_weak("AAPL", "2026-08-25") is True

    def test_neutral_does_not_flag_weak(self):
        with patch(f"{_MODULE}.DatabaseContext", return_value=_db_context_returning(("neutral",))):
            assert _check_sector_weak("AAPL", "2026-08-25") is False

    def test_mild_defensive_lead_does_not_flag_weak(self):
        with patch(f"{_MODULE}.DatabaseContext", return_value=_db_context_returning(("mild_defensive_lead",))):
            assert _check_sector_weak("AAPL", "2026-08-25") is False

    def test_no_row_for_date_does_not_flag_weak(self):
        with patch(f"{_MODULE}.DatabaseContext", return_value=_db_context_returning(None)):
            assert _check_sector_weak("AAPL", "2026-08-25") is False

    def test_query_is_not_scoped_to_candidates_own_sector(self):
        """The core bug: this must query the single 'market_rotation' row directly, not join
        against company_profile for the candidate's own sector (which could never match)."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = ("severe_defensive_rotation",)
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False
        with patch(f"{_MODULE}.DatabaseContext", return_value=mock_ctx):
            result = _check_sector_weak("AAPL", "2026-08-25")
        assert result is True
        # Exactly one query (the sector_rotation_signal lookup) - no company_profile join.
        assert mock_cur.execute.call_count == 1
        executed_sql = mock_cur.execute.call_args[0][0]
        assert "market_rotation" in executed_sql
        assert "company_profile" not in executed_sql
