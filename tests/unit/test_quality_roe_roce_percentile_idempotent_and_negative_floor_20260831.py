"""Regression tests for update_quality_sector_neutral_scores() (loaders/helpers/
vqg_quality_batch.py): idempotency and the negative-ROE floor.

REBUILT 2026-09-17 (factor-purity pivot: MSCI -> AQR only - see vqg_quality_batch.py's own
docstring for the full citation, Asness/Frazzini/Pedersen 2019 "Quality Minus Junk") to use
the new row shape and the real 3-leg construction (Profitability/Safety/Payout - the Growth
leg was dropped the same day Growth was restored as its own top-level BASE_PILLAR_WEIGHTS
pillar, see pillar_weights.py's "ABOVE DECISION SUPERSEDED" note), but the two properties this
file pins are unchanged by that rewrite and remain load-bearing:

1. IDEMPOTENCY: this pass is a pure function of the raw stored ratio columns - quality_score
   is only ever a WRITE target, never also a read input (see git history, commit fixing the
   original additive-delta non-idempotence bug, for why this matters: three consecutive runs
   with zero underlying data change used to drift scores upward every time via
   `quality_score_NEW = quality_score_OLD + delta`).
2. NEGATIVE ROE FLOOR: a negative raw ROE (or the sign-flip-distress case) must not rank
   favorably just because a z-score has no inherent floor the way a curve does.

Row shape (matches the real SELECT in update_quality_sector_neutral_scores() exactly):
(symbol, roe, roa, debt_to_equity, quality_score_old, earnings_variability,
 gross_profitability, gross_margin, accruals_ratio, net_payout_yield).
"""

from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader as L


def _row(
    symbol: str,
    roe: float | None,
    roa: float | None,
    debt_to_equity: float | None,
    earnings_variability: float | None,
    gross_profitability: float | None = None,
    gross_margin: float | None = None,
    accruals_ratio: float | None = None,
    quality_score_old: float = 1.0,
) -> tuple:
    return (
        symbol,
        roe,
        roa,
        debt_to_equity,
        quality_score_old,
        earnings_variability,
        gross_profitability,
        gross_margin,
        accruals_ratio,
        None,  # net_payout_yield
    )


def _run_with_mocked_rows(rows: list[tuple]) -> list[tuple[str, float]]:
    """Run update_quality_sector_neutral_scores() against a fully mocked DB returning `rows`
    for the correction SELECT (and [] for _withhold_quality_below_floor()'s own SELECT), and
    return the UPDATE's (symbol, quality_score) pairs, or [] if no UPDATE was issued."""
    mock_cur = MagicMock()
    mock_cur.fetchall.side_effect = [rows, []]
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


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """The defining symptom of the old additive-delta bug: feed the function's OWN prior
        output back in as quality_score (simulating a second consecutive run with zero
        underlying data change) and it must NOT drift further - a fixed point, not a ratchet."""
        # Two symbols, each with enough legs available (Profitability + Safety) to clear
        # QUALITY_MIN_LEGS_AVAILABLE, so z-scores aren't the single-symbol neutral-50.0
        # special case.
        row_a = _row(
            "A",
            roe=20.0,
            roa=10.0,
            debt_to_equity=0.5,
            earnings_variability=10.0,
            gross_profitability=20.0,
            gross_margin=40.0,
            accruals_ratio=1.0,
        )
        row_b = _row(
            "B",
            roe=-18.31,
            roa=-1.68,
            debt_to_equity=0.0,
            earnings_variability=0.87,
            gross_profitability=5.0,
            gross_margin=15.0,
            accruals_ratio=8.0,
        )

        first_pass_updates = _run_with_mocked_rows([row_a, row_b])
        assert first_pass_updates, "expected the first pass to correct the placeholder quality_score"
        corrected = dict(first_pass_updates)

        row_a_2 = _row(
            "A",
            roe=20.0,
            roa=10.0,
            debt_to_equity=0.5,
            earnings_variability=10.0,
            gross_profitability=20.0,
            gross_margin=40.0,
            accruals_ratio=1.0,
            quality_score_old=corrected["A"],
        )
        row_b_2 = _row(
            "B",
            roe=-18.31,
            roa=-1.68,
            debt_to_equity=0.0,
            earnings_variability=0.87,
            gross_profitability=5.0,
            gross_margin=15.0,
            accruals_ratio=8.0,
            quality_score_old=corrected["B"],
        )
        second_pass_updates = _run_with_mocked_rows([row_a_2, row_b_2])

        assert second_pass_updates == [], (
            "re-running with unchanged raw inputs and the prior run's own output must not "
            f"change quality_score again (got {second_pass_updates}) - this is the exact "
            "non-idempotence/compounding bug this fix closes"
        )

    def test_three_consecutive_runs_converge_not_drift(self) -> None:
        """Broader sanity check across more symbols, including a negative-ROE one - three
        passes in a row must reach a fixed point by pass 2, never keep moving."""
        rows = [
            _row(
                "POS",
                roe=25.0,
                roa=12.0,
                debt_to_equity=0.3,
                earnings_variability=5.0,
                gross_profitability=25.0,
                gross_margin=45.0,
                accruals_ratio=0.5,
            ),
            _row(
                "NEG",
                roe=-30.0,
                roa=-10.0,
                debt_to_equity=1.0,
                earnings_variability=20.0,
                gross_profitability=3.0,
                gross_margin=10.0,
                accruals_ratio=9.0,
            ),
            _row(
                "MIX",
                roe=5.0,
                roa=3.0,
                debt_to_equity=0.8,
                earnings_variability=15.0,
                gross_profitability=10.0,
                gross_margin=20.0,
                accruals_ratio=4.0,
            ),
        ]

        def _next_pass_rows(prior_rows: list[tuple], prior_updates: dict[str, float]) -> list[tuple]:
            return [(*r[:4], prior_updates.get(r[0], r[4]), *r[5:]) for r in prior_rows]

        pass1 = dict(_run_with_mocked_rows(rows))
        rows_after_1 = _next_pass_rows(rows, pass1)
        pass2 = dict(_run_with_mocked_rows(rows_after_1))
        rows_after_2 = _next_pass_rows(rows_after_1, pass2)
        pass3_updates = _run_with_mocked_rows(rows_after_2)

        assert pass3_updates == [], f"score kept drifting on a 3rd identical pass: {pass3_updates}"


class TestNegativeRoeFloor:
    def test_deeply_negative_roe_does_not_inflate_quality_score(self) -> None:
        """A company with deeply negative ROE (and the ROA sign-flip guard both negative)
        must NOT land anywhere near a strong peer's score."""
        rows = [
            _row(
                "GOOD",
                roe=25.0,
                roa=15.0,
                debt_to_equity=0.2,
                earnings_variability=3.0,
                gross_profitability=22.0,
                gross_margin=42.0,
                accruals_ratio=1.0,
            ),
            _row(
                "BAD",
                roe=-18.31,
                roa=-9.55,
                debt_to_equity=0.72,
                earnings_variability=11.66,
                gross_profitability=4.0,
                gross_margin=12.0,
                accruals_ratio=7.5,
            ),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert "BAD" in updates
        assert updates["BAD"] < updates["GOOD"]
        assert updates["BAD"] < 40.0, f"a company with negative ROE scored {updates['BAD']}, expected clearly low"

    def test_negative_roe_floors_to_worst_not_a_lenient_percentile(self) -> None:
        """Direct check: a negative-ROE (sign-flip-distress) symbol's ROE contribution to the
        Profitability leg must compute as the WORST z-score (-3.0), not get ranked among the
        real population the way a plain percentile-of-all-values might rank a merely-bad (not
        literally worst) raw value favorably. Both symbols share identical gross_profitability/
        gross_margin/accruals_ratio (only ROE/ROA differ), so any score gap must come purely
        from the ROE sign-flip floor, not from the other Profitability sub-components."""
        # debt_to_equity/earnings_variability (Safety leg) AND roa/gross_profitability/
        # gross_margin/accruals_ratio (the OTHER Profitability sub-components, including the
        # algebraically-derived CFOA = roa - accruals_ratio) are all identical for both
        # symbols - only the raw ROE magnitude differs. The sign-flip guard only depends on
        # roe<0 (both here) or roa<0 (both here too), so both must get an IDENTICAL -3.0 ROE
        # contribution regardless of exactly how negative each one's own ROE is.
        rows = [
            _row(
                "WORST_NEG",
                roe=-40.0,
                roa=-3.0,
                debt_to_equity=0.5,
                earnings_variability=10.0,
                gross_profitability=10.0,
                gross_margin=20.0,
                accruals_ratio=2.0,
            ),
            _row(
                "MID_NEG",
                roe=-5.0,
                roa=-3.0,
                debt_to_equity=0.5,
                earnings_variability=10.0,
                gross_profitability=10.0,
                gross_margin=20.0,
                accruals_ratio=2.0,
            ),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        # Both sign-flip-floor to the same worst ROE contribution (-3.0) within the
        # Profitability leg, and share every other sub-component - with no differentiating
        # input, they must tie.
        assert updates["WORST_NEG"] == updates["MID_NEG"]
