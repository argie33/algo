"""Regression tests for update_quality_sector_neutral_scores() (loaders/helpers/
vqg_quality_batch.py): idempotency and the negative-ROE floor.

REBUILT 2026-09-16 (factor-purity sweep, MSCI 3-variable Quality Index rebuild - see
vqg_quality_batch.py's own docstring for the full citation) to use the new row shape and
scored legs (ROE/Debt-to-Equity/Earnings Variability), but the two properties this file pins
are unchanged by that rewrite and remain load-bearing:

1. IDEMPOTENCY: this pass is a pure function of the raw stored ratio columns - quality_score
   is only ever a WRITE target, never also a read input (see git history, commit fixing the
   original additive-delta non-idempotence bug, for why this matters: three consecutive runs
   with zero underlying data change used to drift scores upward every time via
   `quality_score_NEW = quality_score_OLD + delta`).
2. NEGATIVE ROE FLOOR: a negative raw ROE (or the sign-flip-distress case) must not rank
   favorably just because a percentile/z-score has no inherent floor at 0 the way a curve does.
"""

from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader as L


def _row(
    symbol: str,
    roe: float | None,
    roa: float | None,
    debt_to_equity: float | None,
    earnings_variability: float | None,
    quality_score_old: float = 1.0,
    sector: str = "Technology",
) -> tuple:
    return (
        symbol,
        sector,
        None,  # industry
        roe,
        roa,
        None,  # roce_pct
        None,  # fcf_margin
        debt_to_equity,
        None,  # margin_volatility
        None,  # asset_turnover
        None,  # gross_profitability
        quality_score_old,
        False,  # is_fpi
        None,  # market_cap
        earnings_variability,
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
        # Two symbols so z-scores aren't the single-symbol neutral-50.0 special case.
        row_a = _row("A", roe=20.0, roa=10.0, debt_to_equity=0.5, earnings_variability=10.0)
        row_b = _row("B", roe=-18.31, roa=-1.68, debt_to_equity=0.0, earnings_variability=0.87)

        first_pass_updates = _run_with_mocked_rows([row_a, row_b])
        assert first_pass_updates, "expected the first pass to correct the placeholder quality_score"
        corrected = dict(first_pass_updates)

        row_a_2 = _row(
            "A",
            roe=20.0,
            roa=10.0,
            debt_to_equity=0.5,
            earnings_variability=10.0,
            quality_score_old=corrected["A"],
        )
        row_b_2 = _row(
            "B",
            roe=-18.31,
            roa=-1.68,
            debt_to_equity=0.0,
            earnings_variability=0.87,
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
            _row("POS", roe=25.0, roa=12.0, debt_to_equity=0.3, earnings_variability=5.0),
            _row("NEG", roe=-30.0, roa=-10.0, debt_to_equity=1.0, earnings_variability=20.0),
            _row("MIX", roe=5.0, roa=3.0, debt_to_equity=0.8, earnings_variability=15.0),
        ]

        def _next_pass_rows(prior_rows: list[tuple], prior_updates: dict[str, float]) -> list[tuple]:
            return [(*r[:11], prior_updates.get(r[0], r[11]), *r[12:]) for r in prior_rows]

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
            _row("GOOD", roe=25.0, roa=15.0, debt_to_equity=0.2, earnings_variability=3.0),
            _row("BAD", roe=-18.31, roa=-9.55, debt_to_equity=0.72, earnings_variability=11.66),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert "BAD" in updates
        assert updates["BAD"] < updates["GOOD"]
        assert updates["BAD"] < 40.0, f"a company with negative ROE scored {updates['BAD']}, expected clearly low"

    def test_negative_roe_floors_to_worst_not_a_lenient_percentile(self) -> None:
        """Direct check: a negative-ROE (sign-flip-distress) symbol's ROE leg must compute as
        the WORST z-score (-3.0, MSCI's own winsorization bound), not get ranked among the
        real population the way a plain percentile-of-all-values might rank a merely-bad (not
        literally worst) raw value favorably."""
        rows = [
            _row("WORST_NEG", roe=-40.0, roa=-30.0, debt_to_equity=None, earnings_variability=None),
            _row("MID_NEG", roe=-5.0, roa=-3.0, debt_to_equity=None, earnings_variability=None),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        # Both sign-flip-floor to the same worst z-score (-3.0) on the ROE leg (their only
        # scored leg - D/E and Earnings Variability are both missing for both) - with no
        # differentiating leg, they must tie, both at the sector-relative floor.
        assert updates["WORST_NEG"] == updates["MID_NEG"]
