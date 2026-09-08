"""Regression test for the 2026-09-07 fix (goal: "huge scoring bug" audit, common-sense
sweep of the Quality leaderboard) to what is now update_quality_sector_neutral_scores()
(loaders/load_value_quality_growth_metrics.py) - renamed and generalized to all 8 Quality
components/all sectors by the same-day "best and brightest" scoring-methodology rewrite, but
the sign-flip guard this file tests is unchanged by that rewrite.

Live-confirmed on the real local DB: a LOSS-MAKING company (negative net_income, i.e.
negative ROA - total_assets is never negative, so ROA's sign always matches net income's)
can only show a POSITIVE ROE when shareholders_equity is ALSO negative (double negative
flips positive) - a distressed/eroded-equity balance sheet, not genuine profitability. 274
universe symbols hit this shape (202 with roe>=100%): ROC (roe=915.88%, roa=-38.43%), ALTG
(roe=912.50%, roa=-6.01%), ECOR (roe=817.20%, roa=-74.82%) among them - all winning
near-top ROE percentile purely off this artifact, the same "single most extreme raw value
wins percentile 100 outright" bug class already fixed for Value's MIN_PLAUSIBLE_PB_RATIO/
PS_RATIO/PE_RATIO, just never guarded here before this fix.

Deliberately keyed on `roa`'s sign, not a raw magnitude ceiling: a genuinely profitable
company with small-but-positive equity from heavy historical buybacks (e.g. real-world
HRB/CVLT, both roe>500% with POSITIVE roa) is a legitimate, if extreme, value and must
stay rankable - only the sign-flipped (profitable-looking ROE despite an actual loss)
case is excluded.
"""

from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader as L


def _run_with_mocked_rows(rows: list[tuple]) -> list[tuple[str, float]]:
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
        return []
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return list(updates)


class TestRoeSignFlipDistressArtifactExcluded:
    def test_positive_roe_with_negative_roa_floored_like_negative_roe(self) -> None:
        """ROC-shaped case: roe=915.88 (positive) but roa=-38.43 (a real loss) - the ROE
        term must contribute 0, the same as a directly-negative ROE, not win a high
        percentile off the sign-flip artifact."""
        rows = [
            # genuinely profitable peer
            ("GOOD", "Technology", None, 25.0, 15.0, 20.0, 12.0, 0.2, 3.0, 90.0, 35.0, 999.0),
            ("ROC_SHAPED", "Technology", None, 915.88, -38.43, None, None, None, None, None, None, 999.0),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert "ROC_SHAPED" in updates
        # ROC_SHAPED's only components are roe (floored to 0, sign-flip guard) and roa
        # (negative, floors to 0 too) - quality_score must be 0.0, not inflated by the fake
        # "best ROE" rank.
        assert updates["ROC_SHAPED"] == 0.0

    def test_positive_roe_with_positive_roa_still_ranks_normally(self) -> None:
        """HRB/CVLT-shaped case: roe is extreme (>500%) but roa is genuinely positive (real
        profit, just a small buyback-thinned equity base) - must NOT be excluded from the
        ranking the way the distress-artifact case above is."""
        rows = [
            ("LOWER_REAL_ROE", "Technology", None, 20.0, 10.0, None, None, None, None, None, None, 0.0),
            ("HRB_SHAPED", "Technology", None, 624.40, 18.59, None, None, None, None, None, None, 0.0),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        # Both are real, non-negative roe/roa - HRB_SHAPED has the higher roe AND roa, so its
        # sector-neutral z-score (and therefore composite) must come out higher, not be
        # floored to 0.
        assert updates["HRB_SHAPED"] > updates["LOWER_REAL_ROE"]

    def test_roe_positive_but_roa_missing_omits_roe_component(self) -> None:
        """Edge case live-confirmed on 6 universe symbols: roe is real and non-negative but
        roa is NULL. Missing roa can't verify the sign-flip artifact either way, but it's
        also not evidence of distress - an extraction gap, not a loss. The ROE component
        must be OMITTED (like every other component in this loop when its input is
        missing), never flip roe to a hard 0 and consume its full weight for an unrelated
        data gap (2026-09-07 real-money-readiness audit fix). With every other input also
        missing here, total_weight is 0 and the symbol gets no update at all."""
        rows = [("NOROA", "Technology", None, 30.0, None, None, None, None, None, None, None, 999.0)]
        updates = dict(_run_with_mocked_rows(rows))
        assert "NOROA" not in updates

    def test_roe_positive_roa_missing_other_components_present_not_penalized(self) -> None:
        """Same missing-roa shape as above, but with another real component present
        (fcf_margin) so the row does produce a score - that score must reflect ONLY the real
        component, never a floored-to-0 ROE term dragging it down for the unrelated roa gap.
        fcf_margin is alone in its sector-neutral z-score pool (no peer) -> neutral z=0.0 ->
        percentile 50.0, weight 15 as the only component, so the composite equals it exactly."""
        rows = [("NOROA_WITH_FCF", "Technology", None, 30.0, None, None, 20.0, None, None, None, None, 999.0)]
        updates = dict(_run_with_mocked_rows(rows))
        assert updates["NOROA_WITH_FCF"] == 50.0
