"""Verification test (2026-08-25, real-money-readiness goal session - closing a specific
test-coverage gap): proves, by actually calling PreTradeChecks.run_all() with a mocked
sector/industry count already AT the configured cap, that max_positions_per_sector and
max_positions_per_industry genuinely reject a new entry - not just that the code reads the
config values (already covered by other tests), but that a real breach scenario is rejected.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.trading.pretrade_checks import PreTradeChecks


def _config(max_sector=3, max_industry=5):
    return {
        "max_position_size_pct": 50.0,  # loose, isolate the sector/industry check alone
        "min_order_size_dollars": 100,
        "max_positions_per_sector": max_sector,
        "max_positions_per_industry": max_industry,
        # Loose caps for the downstream top-5-concentration check (algo/trading/
        # pretrade_checks.py's _check_top5_concentration) - reached by run_all() even in the
        # "passes" case (unlike correlation/beta, which fail open on the empty open-position
        # list this test's mock provides), and required (no default) once execution gets there.
        "max_top5_concentration_pct": 100.0,
    }


def _mock_db_context(sector, industry, sector_count, industry_count):
    """Mirrors run_all()'s real query order: duplicate check, symbol-found check, then
    sector/industry lookup, then sector count, then industry count.

    fetchall() defaults to [] so that IF execution reaches the correlation/beta/top5-
    concentration checks added later in run_all() (only relevant for the "passes" case -
    the rejection tests return before ever reaching them), each sees "no open positions"
    and fails open immediately, matching those checks' own documented fast path - avoids
    having to hand-craft mock data for every downstream check just to test the sector/
    industry check in isolation.
    """
    fixed_responses = [
        None,  # Check 1: no open algo_positions row
        None,  # Check 1b: no open algo_trades row
        None,  # Check 2: no recently-closed position
        (True,),  # symbol found in universe (truthy row)
        (sector, industry),  # company_profile sector/industry
        (sector_count,),  # sector concentration count
        (industry_count,),  # industry concentration count
    ]
    call_count = {"n": 0}

    def _fetchone(*_args, **_kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        # Beyond the fixed sequence (only reached once execution passes sector/industry and
        # continues into correlation/beta/top5-concentration - only relevant for the
        # "passes" case), return None so each of those checks' own "no data" fail-open path
        # takes over rather than needing a hand-crafted response for every downstream query.
        return fixed_responses[idx] if idx < len(fixed_responses) else None

    mock_cur = MagicMock()
    mock_cur.fetchone.side_effect = _fetchone
    mock_cur.fetchall.return_value = []
    mock_db_context = MagicMock()
    mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
    mock_db_context.__exit__ = MagicMock(return_value=False)
    return mock_db_context


class TestSectorConcentrationBreach:
    def test_sector_at_cap_rejects_new_entry(self):
        """3 open positions already in Technology, cap is 3 -> a 4th must be rejected."""
        checks = PreTradeChecks(config=_config(max_sector=3, max_industry=100))
        mock_earnings = MagicMock()
        mock_earnings.run.return_value = {"pass": True, "reason": None}
        db_ctx = _mock_db_context(sector="Technology", industry="Software", sector_count=3, industry_count=0)

        with (
            patch("algo.trading.pretrade_checks.EarningsBlackout", return_value=mock_earnings),
            patch("algo.trading.pretrade_checks.DatabaseContext", return_value=db_ctx),
        ):
            passed, reason = checks.run_all(
                symbol="AAPL", position_value=1000.0, portfolio_value=100_000.0, side="BUY", eval_date=date(2026, 3, 15)
            )

        assert passed is False, f"expected sector-at-cap rejection, got passed=True reason={reason!r}"
        assert reason is not None and "Technology" in reason and "3" in reason

    def test_sector_below_cap_passes(self):
        """2 open positions in Technology, cap is 3 -> a 3rd is still allowed."""
        checks = PreTradeChecks(config=_config(max_sector=3, max_industry=100))
        mock_earnings = MagicMock()
        mock_earnings.run.return_value = {"pass": True, "reason": None}
        db_ctx = _mock_db_context(sector="Technology", industry="Software", sector_count=2, industry_count=0)

        with (
            patch("algo.trading.pretrade_checks.EarningsBlackout", return_value=mock_earnings),
            patch("algo.trading.pretrade_checks.DatabaseContext", return_value=db_ctx),
        ):
            passed, reason = checks.run_all(
                symbol="AAPL", position_value=1000.0, portfolio_value=100_000.0, side="BUY", eval_date=date(2026, 3, 15)
            )

        assert passed is True, f"expected approval below the sector cap, got passed=False reason={reason!r}"


class TestIndustryConcentrationBreach:
    def test_industry_at_cap_rejects_new_entry(self):
        """5 open positions already in Software, cap is 5 -> a 6th must be rejected, even
        though the sector itself is nowhere near its own (looser) cap."""
        checks = PreTradeChecks(config=_config(max_sector=100, max_industry=5))
        mock_earnings = MagicMock()
        mock_earnings.run.return_value = {"pass": True, "reason": None}
        db_ctx = _mock_db_context(sector="Technology", industry="Software", sector_count=1, industry_count=5)

        with (
            patch("algo.trading.pretrade_checks.EarningsBlackout", return_value=mock_earnings),
            patch("algo.trading.pretrade_checks.DatabaseContext", return_value=db_ctx),
        ):
            passed, reason = checks.run_all(
                symbol="MSFT", position_value=1000.0, portfolio_value=100_000.0, side="BUY", eval_date=date(2026, 3, 15)
            )

        assert passed is False, f"expected industry-at-cap rejection, got passed=True reason={reason!r}"
        assert reason is not None and "Software" in reason and "5" in reason
