"""Regression test: update_quality_sector_neutral_scores() (loaders/helpers/vqg_quality_batch.py)
must exclude fcf_margin for depository banks/insurance underwriters/regulated utilities, the same
exclusion Pass-1's curve-based fcf_margin_score already applies (vqg_quality.py) and that a
2026-09-07 session live-confirmed against the real DB (JPM fcf_margin=-81.00%, GS=-81.02%,
WFC=-22.70%, C=-87.01%, NEE=-42%, XEL=-46%, D=-44%) - these are balance-sheet/capex artifacts of
the metric definition for these industries, not real profitability signals.

The 2026-09-08 sector-neutral-zscore rewrite made this method the SOLE authoritative source of
quality_score but initially dropped this exclusion (dry-run against live DB reproduced the exact
regression: JPM 67.45->28.53, WFC 55.40->27.07, NEE 60.47->36.98 driven by a deeply negative
fcf_margin being floored to 0 at 15% weight) - this test locks in the fix that carries the
exclusion forward from Pass-1 into the batch z-score pass.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader as L


def _run_with_mocked_rows(rows: list[tuple[Any, ...]]) -> dict[str, float]:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    with (
        patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_ctx,
        patch("loaders.load_value_quality_growth_metrics.execute_values") as mock_execute_values,
    ):
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)
        loader.update_quality_sector_neutral_scores()
    if not mock_execute_values.called:
        return {}
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return dict(updates)


class TestFcfMarginExcludedForBankUtilityIndustries:
    def test_bank_deeply_negative_fcf_margin_not_floored_to_zero(self) -> None:
        """JPM-shaped: real, solid roe/roa/roce/d2e but fcf_margin=-81% (loan-origination
        noise, not distress). With fcf_margin excluded, the symbol's score must reflect only
        its real components - never zeroed out by the excluded metric."""
        rows = [
            (
                "JPM_SHAPED",
                "Financial Services",
                "National Commercial Banks",
                15.74,
                1.29,
                3.85,
                -81.0,
                11.21,
                0.77,
                4.12,
                None,
                999.0,
            ),
            (
                "PEER_BANK",
                "Financial Services",
                "National Commercial Banks",
                10.0,
                1.0,
                3.0,
                11.0,
                10.0,
                0.7,
                4.0,
                None,
                999.0,
            ),
        ]
        updates = _run_with_mocked_rows(rows)
        assert "JPM_SHAPED" in updates
        # Would be pulled toward 0 by a floored 15%-weight fcf_margin term if not excluded -
        # instead it must land near/above the sector-neutral midpoint given otherwise-solid
        # roe/roa/roce/d2e inputs.
        assert updates["JPM_SHAPED"] > 40.0

    def test_utility_deeply_negative_fcf_margin_not_floored_to_zero(self) -> None:
        """NEE-shaped: continuous grid capex drives fcf_margin deeply negative for a
        fundamentally healthy, dividend-growing utility - must not be scored as distress."""
        rows = [
            (
                "NEE_SHAPED",
                "Utilities",
                "Electric Services",
                12.52,
                3.21,
                5.48,
                -42.2,
                1.77,
                1.30,
                12.89,
                10.35,
                999.0,
            ),
            (
                "PEER_UTIL",
                "Utilities",
                "Electric Services",
                9.0,
                2.5,
                4.0,
                -40.0,
                1.8,
                2.0,
                14.0,
                9.0,
                999.0,
            ),
        ]
        updates = _run_with_mocked_rows(rows)
        assert "NEE_SHAPED" in updates
        assert updates["NEE_SHAPED"] > 40.0

    def test_non_excluded_industry_still_floors_negative_fcf_margin(self) -> None:
        """Sanity check the exclusion is industry-scoped, not a blanket bypass: an ordinary
        Technology company with a real deeply negative fcf_margin must still be floored to 0
        for that component, same as before this fix."""
        rows = [
            ("TECH_GOOD", "Technology", "Prepackaged Software", 20.0, 10.0, 15.0, 20.0, 0.3, 3.0, 40.0, 30.0, 999.0),
            (
                "TECH_BURN",
                "Technology",
                "Prepackaged Software",
                20.0,
                10.0,
                15.0,
                -50.0,
                0.3,
                3.0,
                40.0,
                30.0,
                999.0,
            ),
        ]
        updates = _run_with_mocked_rows(rows)
        # TECH_BURN's fcf_margin term floors to 0 (not excluded, not in a bank/utility
        # industry) so it must score strictly lower than the otherwise-identical TECH_GOOD.
        assert updates["TECH_BURN"] < updates["TECH_GOOD"]

    def test_missing_industry_column_fails_open_to_no_exclusion(self) -> None:
        """A row with industry=None (e.g. a company_profile LEFT JOIN miss) must not crash
        and must fail open exactly like _get_symbol_industry's own documented contract -
        fcf_margin is scored normally, not silently excluded."""
        rows = [("NOIND", "Financial Services", None, 15.0, 1.0, 3.0, -81.0, 11.0, 0.8, 4.0, None, 999.0)]
        updates = _run_with_mocked_rows(rows)
        assert "NOIND" in updates
        # fcf_margin is alone in its z-score pool -> neutral z=0.0 -> percentile 50, but it's
        # floored to 0 (negative, not excluded) - the other 3 real components (roe/roa/roce)
        # are also each alone in their pools -> percentile 50 each. Weighted avg of
        # roe=50(w11)+roa=50(w18)+roce=50(w18)+fcf=0(w15)+d2e=50(w18)+margin_vol=50(w7)+
        # asset_turnover=50(w7) over total weight 94 must be well below 50, proving fcf_margin
        # was NOT excluded here.
        assert updates["NOIND"] < 50.0
