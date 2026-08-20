"""Regression test: total_debt/total_cash/ebitda/enterprise_value are NUMERIC(15,2) columns
(max abs value < 10^13, i.e. $10 trillion) but were written with no sanity bound - unlike
pe_ratio/pb_ratio/ps_ratio/ev_ebitda/ev_revenue in the same function, which all already have
explicit bounds. Live-confirmed 2026-08-16: BBAR/BCH/BMA/BSAC/HDB/HMC (all foreign ADR filers)
hit NumericValueOutOfRange on this exact column class, crashing the whole sec_valuations INSERT
and losing every other computed ratio for that symbol too - same root cause (foreign filers
reporting balance-sheet figures in local currency without USD conversion) already documented for
loaders/load_value_quality_growth_metrics.py's MAX_ABSOLUTE_DOLLAR_VALUE guard.

FIXED 2026-08-20 (goal: finance-accuracy audit): the original $1 trillion ceiling's own comment
("no real company exceeds this") was already false when read - live-confirmed 14 real, major
companies (NVDA $5.30T, AAPL $4.74T, GOOGL $4.18T, MSFT $3.60T, AMZN $2.87T, and more) computing
a real, well-formed enterprise_value that this guard was silently nulling, along with
ev_ebitda/ev_revenue for every one of them. Raised to $9 trillion - safely under the real
NUMERIC(15,2) column overflow point (~$10T, confirmed via information_schema) while admitting
every real company's current scale. See test_mega_cap_enterprise_value_not_rejected below.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader():
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestForeignFilerOverflowBound:
    def test_implausible_total_debt_marked_unavailable_not_crashed(self):
        loader = _make_loader()
        # BBAR-shaped: a foreign filer's local-currency debt figure many orders of magnitude
        # past any real company - would overflow the NUMERIC(15,2) column (max abs < $10T).
        result = loader._compute_valuations(
            symbol="BBAR",
            current_price=10.0,
            shares_out=100_000_000.0,
            ttm_eps=1.0,
            ttm_revenue=500_000_000.0,
            book_value=200_000_000.0,
            ocf=50_000_000.0,
            capex=10_000_000.0,
            prior_year_eps=0.9,
            dividends_paid=None,
            total_debt=50_000_000_000_000.0,
            total_cash=1_000_000.0,
            ebitda=100_000_000.0,
        )

        assert result["total_debt"] is None
        assert result["enterprise_value"] is None

    def test_implausible_ebitda_marked_unavailable_not_crashed(self):
        loader = _make_loader()
        result = loader._compute_valuations(
            symbol="HDB",
            current_price=60.0,
            shares_out=3_000_000_000.0,
            ttm_eps=3.0,
            ttm_revenue=20_000_000_000.0,
            book_value=15_000_000_000.0,
            ocf=5_000_000_000.0,
            capex=1_000_000_000.0,
            prior_year_eps=2.8,
            dividends_paid=None,
            total_debt=10_000_000_000.0,
            total_cash=2_000_000_000.0,
            ebitda=50_000_000_000_000.0,
        )

        assert result["ebitda"] is None

    def test_normal_values_still_compute(self):
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

        assert result["total_debt"] == 200_000_000.0
        assert result["total_cash"] == 50_000_000.0
        assert result["ebitda"] == 150_000_000.0
        assert result["enterprise_value"] is not None

    def test_mega_cap_enterprise_value_not_rejected(self):
        """GOOGL-shaped: a real mega-cap with enterprise_value in the trillions must not be
        treated as a data error - only the genuine currency-scale-mismatch class (tens/hundreds
        of trillions and up) should be rejected."""
        loader = _make_loader()
        result = loader._compute_valuations(
            symbol="GOOGL",
            current_price=345.67,
            shares_out=12_083_000_000.0,
            ttm_eps=10.5,
            ttm_revenue=350_000_000_000.0,
            book_value=300_000_000_000.0,
            ocf=120_000_000_000.0,
            capex=50_000_000_000.0,
            prior_year_eps=9.0,
            dividends_paid=None,
            total_debt=20_627_000_000.0,
            total_cash=55_911_000_000.0,
            ebitda=150_175_000_000.0,
        )

        # market_cap ~= $4.18T, enterprise_value ~= market_cap + debt - cash, comfortably
        # within the raised $9T ceiling and the real NUMERIC(15,2) column's ~$10T limit.
        assert result["enterprise_value"] is not None
        assert result["enterprise_value"] > 4_000_000_000_000.0
        assert result["ev_ebitda"] is not None
