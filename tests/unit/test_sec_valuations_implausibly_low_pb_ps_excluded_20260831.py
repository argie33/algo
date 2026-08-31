"""Regression test for the 2026-08-31 fix: PB/PS ratios had an UPPER sanity bound
(<=1000/<=10000, "Reasonable PB/PS bounds") but no LOWER one - live-confirmed via VCIG (VCI
Global Ltd): pb_ratio=0.01/ps_ratio=0.02, tied for the single cheapest in the whole scored
universe, which won percentile 100 outright in load_stock_scores.py's _percent_rank_cheap_high
and drove VCIG to composite_score's #1 rank ("I don't know why I'm seeing VCIG as top scorer,
it's a shitty stock" - the user's own complaint that triggered this investigation).

Unlike the BMA/LOMA/CEPU/CIG/GGB class this same session fixed in
loaders/load_financial_statements.py (a genuine unconverted-ARS/BRL currency data bug), VCIG's
numbers are independently confirmed REAL: SEC XBRL's own USD-tagged Equity facts ($86.3M
FY2024, $164.1M mid-2025) and a live yfinance snapshot (bookValue=$222.77/share,
priceToBook=0.0096) both agree with the stored ratio - no currency-unit mismatch. That makes
this a ranking-methodology gap, not a data bug: _percent_rank_cheap_high ranks PB/PS purely by
ORDER, so the single most extreme value in the universe - genuine or not - always wins
percentile 100/0 outright. MIN_PLAUSIBLE_PB_RATIO/MIN_PLAUSIBLE_PS_RATIO (0.05) exclude that
tail from the percentile universe entirely (same "skip what's unavailable" treatment every
other missing Value input already gets), mirroring the existing upper-bound rejection exactly.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader():
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestImplausiblyLowPbPsExcluded:
    def test_vcig_shaped_pb_below_floor_excluded(self):
        loader = _make_loader()
        # VCIG-shaped: real USD book value ($86.3M) against a tiny real market cap
        # ($1.38M) - pb_ratio would compute to ~0.016, below MIN_PLAUSIBLE_PB_RATIO (0.05).
        result = loader._compute_valuations(
            symbol="VCIG",
            current_price=2.23,
            shares_out=618_994.0,
            ttm_eps=None,
            ttm_revenue=None,
            book_value=86_321_816.0,
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )
        assert result["pb_ratio"] is None

    def test_bma_shaped_ps_below_floor_excluded(self):
        loader = _make_loader()
        result = loader._compute_valuations(
            symbol="BMATEST",
            current_price=76.05,
            shares_out=62_815_463.0,
            ttm_eps=None,
            ttm_revenue=200_000_000_000.0,  # implausibly large relative to a tiny market cap
            book_value=None,
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )
        assert result["ps_ratio"] is None

    def test_real_deep_value_pb_just_above_floor_still_scores(self):
        """A genuine, if rare, deep-distress case (P/B ~0.1) must NOT be excluded - the
        floor is deliberately conservative (0.05), well below real distressed-equity
        territory."""
        loader = _make_loader()
        result = loader._compute_valuations(
            symbol="DISTRESSCO",
            current_price=10.0,
            shares_out=10_000_000.0,
            ttm_eps=None,
            ttm_revenue=None,
            book_value=1_000_000_000.0,  # bvps=100, pb=0.10
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )
        assert result["pb_ratio"] == 0.10

    def test_normal_pb_ps_unaffected(self):
        loader = _make_loader()
        result = loader._compute_valuations(
            symbol="NORMALCO",
            current_price=100.0,
            shares_out=10_000_000.0,
            ttm_eps=5.0,
            ttm_revenue=500_000_000.0,
            book_value=300_000_000.0,
            ocf=80_000_000.0,
            capex=20_000_000.0,
            prior_year_eps=4.5,
            dividends_paid=None,
            total_debt=200_000_000.0,
            total_cash=50_000_000.0,
            ebitda=150_000_000.0,
        )
        assert result["pb_ratio"] is not None
        assert result["ps_ratio"] is not None

    def test_pb_at_exact_floor_still_included(self):
        """Boundary: exactly MIN_PLAUSIBLE_PB_RATIO must be INCLUDED (>=, not >)."""
        loader = SecValuationsLoader.__new__(SecValuationsLoader)
        result = loader._compute_valuations(
            symbol="EDGECO",
            current_price=5.0,
            shares_out=1_000_000.0,
            ttm_eps=None,
            ttm_revenue=None,
            book_value=100_000_000.0,  # bvps=100, pb=0.05 exactly
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )
        assert result["pb_ratio"] == 0.05


class TestImplausiblyLowPeExcluded:
    """FOLLOW-UP FIX (same session, same day): the PB/PS floor alone did NOT fully fix
    VCIG - live-confirmed after a full remediation + recompute cycle, VCIG's value_score
    was STILL pinned at 100.00 because its pe_ratio is ALSO ~0.01 (VCIG's tiny 618,994
    real shares outstanding inflates EPS the same way it inflates book value per share).
    Same floor, same reasoning, extended to PE."""

    def test_vcig_shaped_pe_below_floor_excluded(self):
        loader = _make_loader()
        # VCIG-shaped: implied EPS ~$223/share (real, tiny-share-count effect) against a
        # ~$2 price - pe_ratio would compute to ~0.01, below MIN_PLAUSIBLE_PE_RATIO (0.05).
        result = loader._compute_valuations(
            symbol="VCIG",
            current_price=2.23,
            shares_out=618_994.0,
            ttm_eps=223.0,
            ttm_revenue=None,
            book_value=None,
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )
        assert result["pe_ratio"] is None

    def test_normal_pe_unaffected(self):
        loader = _make_loader()
        result = loader._compute_valuations(
            symbol="NORMALCO",
            current_price=100.0,
            shares_out=10_000_000.0,
            ttm_eps=5.0,
            ttm_revenue=None,
            book_value=None,
            ocf=None,
            capex=None,
            prior_year_eps=4.5,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )
        assert result["pe_ratio"] == 20.0

    def test_unprofitable_stock_pe_treatment_unaffected(self):
        """ttm_eps == 0 (unprofitable) must still take its own existing path, not the
        new low-PE floor - pe_ratio stays None either way but for the original reason."""
        loader = _make_loader()
        result = loader._compute_valuations(
            symbol="UNPROFITABLECO",
            current_price=10.0,
            shares_out=10_000_000.0,
            ttm_eps=0.0,
            ttm_revenue=None,
            book_value=None,
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )
        assert result["pe_ratio"] is None
