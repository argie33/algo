"""Regression test (2026-09-07, goal: "1600 missing XBRL" reduction sweep / data-accuracy
finding): sec_valuations_ratios.py's _compute_ps_ratio already falls back to an older fiscal
year's revenue when the anchor year's revenue-per-share fails the $0.10 floor (both ps_ratio
and ev_revenue divide by the identical ttm_revenue/shares_out pair), but
sec_valuations_yield_dcf.py's ev_revenue computation never mirrored that fallback - a real,
computable EV/Revenue was silently dropped to None on rows where ps_ratio recovers fine using
an older year.

Live-confirmed ABUS: anchor FY2025 revenue $14.08M against 191.6M shares = $0.0735/share fails
the floor, while ps_ratio=25.29 is real and comes from FY2022's $39.02M/191.6M=$0.2037/share
(the exact fallback this test exercises) - EV/Revenue was left None instead of the equally-
computable ~68.8 from that same year.
"""

from unittest.mock import patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


def _run(symbol, ttm_revenue, entity_shares_out, older_revenue_rows, **overrides):
    loader = _make_loader()
    kwargs = {
        "current_price": 10.0,
        "market_cap": 500_000_000.0,
        "ttm_eps": None,
        "ttm_revenue": ttm_revenue,
        "ocf": None,
        "capex": None,
        "prior_year_eps": None,
        "dividends_paid": None,
        "total_debt": 0.0,
        "total_cash": 0.0,
        "ebitda": None,
        "avg_fcf_fallback": None,
        "beta": None,
        "risk_free_rate": None,
        "entity_shares_out": entity_shares_out,
        "stock_based_compensation": None,
        "dcf_eps_cagr_pct": None,
        "equity_risk_premium": None,
        "net_borrowing": None,
        "common_stock_repurchased": None,
    }
    kwargs.update(overrides)
    with patch("loaders.helpers.sec_valuations_yield_dcf.DatabaseContext") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__.return_value.fetchall.return_value = older_revenue_rows
        mock_db_ctx.return_value.__enter__.return_value.fetchone.return_value = None
        return loader._compute_yield_and_dcf_fields(symbol, **kwargs)


class TestEvRevenueCrossYearFallback:
    def test_anchor_below_floor_falls_back_to_older_year_that_clears_it(self):
        # ABUS-shaped: anchor revenue $14.08M/191.6M shares=$0.0735/share fails the floor;
        # an older year's $39.02M/191.6M=$0.2037/share clears it and yields a plausible ratio.
        result = _run(
            "ABUS",
            ttm_revenue=14_083_000.0,
            entity_shares_out=191_599_600.0,
            older_revenue_rows=[(6_171_000.0,), (18_141_000.0,), (39_019_000.0,)],
            total_debt=746_000.0,
            total_cash=18_008_000.0,
        )

        assert result["ev_revenue"] is not None
        assert result["ev_revenue"] == round(result["enterprise_value"] / 39_019_000.0, 2)

    def test_no_older_year_clears_floor_stays_none(self):
        result = _run(
            "NOFALLBACK",
            ttm_revenue=14_083_000.0,
            entity_shares_out=191_599_600.0,
            older_revenue_rows=[(6_171_000.0,), (18_141_000.0,)],
        )

        assert result["ev_revenue"] is None

    def test_anchor_above_floor_never_triggers_fallback_query(self):
        """A normal, plausible anchor-year computation must not even attempt the fallback
        query - only reached when the primary bound/floor check fails."""
        with patch("loaders.helpers.sec_valuations_yield_dcf.DatabaseContext") as mock_db_ctx:
            loader = _make_loader()
            result = loader._compute_yield_and_dcf_fields(
                "NORMALCO",
                current_price=10.0,
                market_cap=500_000_000.0,
                ttm_eps=None,
                ttm_revenue=100_000_000.0,
                ocf=None,
                capex=None,
                prior_year_eps=None,
                dividends_paid=None,
                total_debt=0.0,
                total_cash=0.0,
                ebitda=None,
                avg_fcf_fallback=None,
                beta=None,
                risk_free_rate=None,
                entity_shares_out=50_000_000.0,
                stock_based_compensation=None,
                dcf_eps_cagr_pct=None,
                equity_risk_premium=None,
                net_borrowing=None,
                common_stock_repurchased=None,
            )

        assert result["ev_revenue"] == round(500_000_000.0 / 100_000_000.0, 2)
        mock_db_ctx.return_value.__enter__.return_value.fetchall.assert_not_called()
