"""Regression test (2026-09-05, goal: "implausible values" sweep): ps_ratio's out-of-bounds
(>10000) rejection in load_sec_valuations.py's _compute_valuations had no cross-year fallback -
same gap class as fcf_margin's cross-year fallback (see
test_fcf_margin_implausible_anchor_cross_year_fallback_20260905.py), just one loader over. The
anchor year's ttm_revenue can be a real but near-zero extraction/reporting artifact even though
an older fiscal year has a real, representative revenue figure that would produce a plausible
ps_ratio when paired with the same current price/shares_out. Live-confirmed via AVTX: was
implausible_ratio pre-fix, now computes a real ps_ratio=2306.76 post-fix.
"""

from decimal import Decimal

from loaders.load_sec_valuations import SecValuationsLoader


class _FakeCursor:
    def __init__(self, revenue_rows):
        self._revenue_rows = revenue_rows

    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return self._revenue_rows

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, revenue_rows):
        self._revenue_rows = revenue_rows

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._revenue_rows)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, revenue_rows):
    # PS ratio computation (with this fallback query) lives in
    # loaders.helpers.sec_valuations_ratios (SecValuationRatiosMixin, extracted from
    # load_sec_valuations.py 2026-09-05, file-size ratchet decomposition) - DatabaseContext
    # must be patched where it's actually imported/used, not in load_sec_valuations itself.
    import loaders.helpers.sec_valuations_ratios as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(revenue_rows))
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestPsRatioImplausibleAnchorCrossYearFallback:
    def test_implausible_anchor_falls_back_to_plausible_older_year(self, monkeypatch):
        # Anchor ttm_revenue is a near-zero artifact: current_price=10, shares_out=1_000_000,
        # ttm_revenue=100 -> rps=0.0001 -> ps=100000 (> 10000 bound). An older fiscal year has
        # real revenue=$5,000,000 -> rps=5.0 -> ps=2.0, plausible.
        loader = _make_loader(monkeypatch, [(Decimal("5000000.00"),)])

        result = loader._compute_valuations(
            symbol="SYM",
            current_price=10.0,
            shares_out=1_000_000.0,
            ttm_eps=None,
            ttm_revenue=100.0,
            book_value=None,
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["ps_ratio"] == 2.0

    def test_implausible_anchor_with_no_plausible_fallback_stays_null(self, monkeypatch):
        # No older year has a plausible pair either - must still null out, not silently pick an
        # equally-bad fallback value.
        loader = _make_loader(monkeypatch, [(Decimal("200.00"),)])

        result = loader._compute_valuations(
            symbol="SYM",
            current_price=10.0,
            shares_out=1_000_000.0,
            ttm_eps=None,
            ttm_revenue=100.0,
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

    def test_immaterial_revenue_per_share_under_10000_ceiling_still_falls_back(self, monkeypatch):
        # Same day, same sweep, follow-up (see pe_ratio's ICUI case): the 10000 ceiling alone
        # doesn't catch every near-zero-per-share blowup. current_price=10, shares_out=
        # 1_000_000, ttm_revenue=50_000 -> rps=0.05 -> ps=200 (UNDER 10000, accepted outright
        # pre-fix). An older year has revenue=$5,000,000 -> rps=5.0 -> ps=2.0, plausible.
        loader = _make_loader(monkeypatch, [(Decimal("5000000.00"),)])

        result = loader._compute_valuations(
            symbol="SYM",
            current_price=10.0,
            shares_out=1_000_000.0,
            ttm_eps=None,
            ttm_revenue=50_000.0,
            book_value=None,
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["ps_ratio"] == 2.0

    def test_immaterial_revenue_fallback_skips_another_immaterial_year(self, monkeypatch):
        # The fallback query includes the anchor year itself - a near-zero anchor rps must
        # not just re-select itself.
        loader = _make_loader(monkeypatch, [(Decimal("50000.00"),), (Decimal("5000000.00"),)])

        result = loader._compute_valuations(
            symbol="SYM",
            current_price=10.0,
            shares_out=1_000_000.0,
            ttm_eps=None,
            ttm_revenue=50_000.0,
            book_value=None,
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["ps_ratio"] == 2.0
