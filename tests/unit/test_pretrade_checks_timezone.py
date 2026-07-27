#!/usr/bin/env python3
"""Regression test for the 2026-07-21 pretrade_checks.py eval_date timezone fix.

run_all() defaulted eval_date via date.today() (system-local calendar date) when the
caller didn't pass one explicitly, then fed it straight into EarningsBlackout.run() - a
documented hard gate that does exact trading-day arithmetic against the earnings date. A
server not running in America/New_York (e.g. UTC in AWS) could evaluate the blackout
window against the wrong calendar day near midnight. Fixed to match the same pattern
already established elsewhere in this codebase (algo/trading/tca.py's record_fill()).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from algo.trading.pretrade_checks import PreTradeChecks
from utils.infrastructure.timezone import EASTERN_TZ


def _config():
    return {
        "max_position_size_pct": 10,
        "min_order_size_dollars": 100,
        "max_positions_per_sector": 5,
        "max_positions_per_industry": 3,
    }


class TestRunAllUsesEasternDateByDefault:
    def test_eval_date_defaults_to_eastern_time_not_system_local(self):
        checks = PreTradeChecks(config=_config())
        expected_eastern_date = datetime.now(EASTERN_TZ).date()

        mock_earnings = MagicMock()
        mock_earnings.run.return_value = {"pass": True, "reason": None}

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None  # no duplicate position, symbol found path varies per call
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with patch("algo.trading.pretrade_checks.EarningsBlackout", return_value=mock_earnings), patch(
            "algo.trading.pretrade_checks.DatabaseContext", return_value=mock_db_context
        ):
            checks.run_all(
                symbol="AAPL",
                position_value=1000.0,
                portfolio_value=100000.0,
                side="BUY",
                eval_date=None,
            )

        mock_earnings.run.assert_called_once()
        called_symbol, called_eval_date = mock_earnings.run.call_args[0]
        assert called_symbol == "AAPL"
        assert called_eval_date == expected_eastern_date

    def test_explicit_eval_date_is_respected_not_overridden(self):
        """An explicitly-passed eval_date (e.g. from a backtest or specific-date check)
        must not be silently replaced by "now"."""
        checks = PreTradeChecks(config=_config())

        from datetime import date

        explicit_date = date(2026, 3, 15)

        mock_earnings = MagicMock()
        mock_earnings.run.return_value = {"pass": True, "reason": None}

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with patch("algo.trading.pretrade_checks.EarningsBlackout", return_value=mock_earnings), patch(
            "algo.trading.pretrade_checks.DatabaseContext", return_value=mock_db_context
        ):
            checks.run_all(
                symbol="AAPL",
                position_value=1000.0,
                portfolio_value=100000.0,
                side="BUY",
                eval_date=explicit_date,
            )

        called_eval_date = mock_earnings.run.call_args[0][1]
        assert called_eval_date == explicit_date


class TestReentryCooldownUsesRealSessionTimezone:
    """Regression test for the 2026-07-27 fix: the flip-flop re-entry cooldown check mislabeled
    a naive `closed_at` (written via SQL CURRENT_TIMESTAMP into a `timestamp without time zone`
    column, so it's in the DB session's local wall-clock timezone, not UTC - confirmed live this
    session's `SHOW timezone` is America/Chicago) as UTC via `.replace(tzinfo=timezone.utc)`.
    That silently inflated minutes_since_close by the session-timezone-to-UTC offset (5+ hours
    for Chicago), so a position closed moments ago always cleared any realistic cooldown -
    defeating the exact same-run re-entry protection this check exists for (Phase 6 exits,
    Phase 8 immediately re-enters). Same bug class already fixed in
    algo/risk/market_exposure.py's cache-age check.
    """

    def _config(self):
        return {
            "max_position_size_pct": 10,
            "reentry_cooldown_minutes": 30,
            "min_order_size_dollars": 100,
            "max_positions_per_sector": 5,
            "max_positions_per_industry": 3,
        }

    def _run(self, closed_at_naive, session_tz_name="America/Chicago", extra_fetches=()):
        checks = PreTradeChecks(config=self._config())

        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            None,  # Check 1: no open algo_positions row
            None,  # Check 1b: no open algo_trades row
            (1, closed_at_naive),  # Check 2: a recently-closed position
            [session_tz_name],  # SHOW timezone
            *extra_fetches,
        ]
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with patch("algo.trading.pretrade_checks.DatabaseContext", return_value=mock_db_context):
            return checks.run_all(
                symbol="AAPL",
                position_value=1000.0,
                portfolio_value=100000.0,
                side="SELL",  # skip the earnings-blackout branch (BUY-only), isolate this check
                eval_date=None,
            )

    def test_position_closed_one_minute_ago_in_chicago_time_is_still_blocked(self):
        """The core bug: a position closed 1 real minute ago (naive Chicago wall-clock, this
        session's actual DB timezone) must still be recognized as recent and blocked by the
        30-minute cooldown - pre-fix, mislabeling it as UTC inflated the computed elapsed time
        to 5+ hours, silently clearing the cooldown and allowing an immediate re-entry."""
        closed_at_naive = datetime.now(ZoneInfo("America/Chicago")).replace(tzinfo=None) - timedelta(minutes=1)

        passed, reason = self._run(closed_at_naive)

        assert passed is False, (
            f"a position closed 1 minute ago must still be inside the 30-minute cooldown, got passed={passed} "
            f"reason={reason!r}"
        )
        assert reason is not None and "cooldown" in reason.lower()

    def test_position_closed_well_outside_cooldown_is_allowed(self):
        """Sanity check: the fix must not make the cooldown block forever - a position closed
        well past the cooldown window must be allowed to re-enter."""
        closed_at_naive = datetime.now(ZoneInfo("America/Chicago")).replace(tzinfo=None) - timedelta(hours=2)

        passed, reason = self._run(
            closed_at_naive,
            extra_fetches=[
                ("AAPL",),  # symbol found in universe
                ("Technology", "Software"),  # company_profile sector/industry
                (0,),  # sector concentration count
                (0,),  # industry concentration count
            ],
        )

        assert passed is True, f"a position closed 2 hours ago must clear a 30-minute cooldown, got {reason!r}"


class _AlgoConfigLike:
    """Minimal stand-in for the real AlgoConfig: config values live in an internal dict,
    exposed via .get()/__getitem__ - NOT as direct Python attributes. This is the shape
    that exposed the getattr() bug below, which every other test in this file (using a
    plain dict) could never catch, since dict.get() already worked correctly."""

    def __init__(self, values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)

    def __getitem__(self, key):
        return self._values[key]


class TestReentryCooldownWorksAgainstRealConfigObjectNotJustPlainDict:
    """CRITICAL FIX regression: the reentry-cooldown check branched on
    isinstance(self.config, dict) and used getattr(self.config, "reentry_cooldown_minutes",
    None) for the non-dict case - but the real AlgoConfig class stores values in
    self._config, never as literal Python attributes, so getattr() always silently
    returned None regardless of what was actually configured in the algo_config table.
    Confirmed live 2026-07-27: a real orchestrator run crashed Phase 8 with "config
    missing" even after the value was correctly seeded in the database, because
    PreTradeChecks receives a real AlgoConfig instance in production, not a plain dict -
    every existing test in this file used a plain dict and could never have caught this.
    """

    def test_cooldown_resolves_from_a_non_dict_config_object(self):
        config = _AlgoConfigLike(
            {
                "max_position_size_pct": 10,
                "reentry_cooldown_minutes": 30,
                "min_order_size_dollars": 100,
                "max_positions_per_sector": 5,
                "max_positions_per_industry": 3,
            }
        )
        checks = PreTradeChecks(config=config)
        closed_at_naive = datetime.now(ZoneInfo("America/Chicago")).replace(tzinfo=None) - timedelta(minutes=1)

        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            None,
            None,
            (1, closed_at_naive),
            ["America/Chicago"],
        ]
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with patch("algo.trading.pretrade_checks.DatabaseContext", return_value=mock_db_context):
            passed, reason = checks.run_all(
                symbol="AAPL",
                position_value=1000.0,
                portfolio_value=100000.0,
                side="SELL",
                eval_date=None,
            )

        assert passed is False, (
            f"a non-dict config object with reentry_cooldown_minutes=30 must still enforce the "
            f"cooldown for a position closed 1 minute ago, got passed={passed} reason={reason!r}"
        )
        assert reason is not None and "cooldown" in reason.lower(), (
            f"expected a cooldown rejection reason, got {reason!r} - if this says 'config missing' "
            f"the getattr() bug against a real (non-dict) config object has regressed"
        )
