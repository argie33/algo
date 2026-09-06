"""Regression test (2026-09-05, goal: "implausible values" sweep): pe_ratio's out-of-bounds
(>10000) and pb_ratio's out-of-bounds (>1000) rejections in load_sec_valuations.py's
_compute_valuations had no cross-year fallback - same gap class as ps_ratio/fcf_margin (see
test_sec_valuations_ps_ratio_implausible_anchor_cross_year_fallback_20260905.py and
test_fcf_margin_implausible_anchor_cross_year_fallback_20260905.py). The anchor year's ttm_eps/
book_value can be a real but near-zero extraction/reporting artifact even though an older fiscal
year has a real, representative figure. Live-confirmed via KLIC: pe_ratio was implausible_ratio
pre-fix, now computes a real pe_ratio=80.81 post-fix.
"""

from decimal import Decimal

from loaders.load_sec_valuations import SecValuationsLoader


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, rows):
        self._rows = rows

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._rows)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, rows):
    # PE/PB ratio computation (with this fallback query) lives in
    # loaders.helpers.sec_valuations_ratios (SecValuationRatiosMixin, extracted from
    # load_sec_valuations.py 2026-09-05, file-size ratchet decomposition) - DatabaseContext
    # must be patched where it's actually imported/used, not in load_sec_valuations itself.
    import loaders.helpers.sec_valuations_ratios as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(rows))
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestPeRatioImplausibleAnchorCrossYearFallback:
    def test_implausible_anchor_falls_back_to_plausible_older_year(self, monkeypatch):
        # Anchor ttm_eps=0.001 -> pe=10000/0.001... rather: current_price=10, ttm_eps=0.0005
        # -> pe=20000 (>10000 bound). An older year has eps=2.0 -> pe=5.0, plausible.
        loader = _make_loader(monkeypatch, [(Decimal("2.00"),)])

        result = loader._compute_valuations(
            symbol="SYM",
            current_price=10.0,
            shares_out=1_000_000.0,
            ttm_eps=0.0005,
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

        assert result["pe_ratio"] == 5.0

    def test_implausible_anchor_with_no_plausible_fallback_stays_null(self, monkeypatch):
        loader = _make_loader(monkeypatch, [(Decimal("0.0001"),)])

        result = loader._compute_valuations(
            symbol="SYM",
            current_price=10.0,
            shares_out=1_000_000.0,
            ttm_eps=0.0005,
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

    def test_immaterial_eps_under_10000_ceiling_still_falls_back(self, monkeypatch):
        # Same day, same sweep, follow-up: the 10000 ceiling alone doesn't catch every
        # near-zero-EPS blowup. Live-confirmed via ICUI: current_price=167.58, anchor
        # ttm_eps=0.03 -> pe=5586 (UNDER 10000, so the original bound accepted it outright).
        # An older year has eps=1.20 -> pe=139.65, plausible - matches the real trailing-
        # 4-quarter EPS ICUI actually has on file.
        loader = _make_loader(monkeypatch, [(Decimal("1.20"),)])

        result = loader._compute_valuations(
            symbol="ICUI",
            current_price=167.58,
            shares_out=1_000_000.0,
            ttm_eps=0.03,
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

        assert result["pe_ratio"] == round(167.58 / 1.20, 2)

    def test_immaterial_eps_fallback_skips_another_immaterial_year(self, monkeypatch):
        # The fallback query includes the anchor year itself (no offset) - an immaterial
        # anchor EPS must not just re-select itself as its own "fallback".
        loader = _make_loader(monkeypatch, [(Decimal("0.03"),), (Decimal("2.00"),)])

        result = loader._compute_valuations(
            symbol="ICUI",
            current_price=167.58,
            shares_out=1_000_000.0,
            ttm_eps=0.03,
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

        assert result["pe_ratio"] == round(167.58 / 2.00, 2)


class TestPbRatioImplausibleAnchorCrossYearFallback:
    def test_implausible_anchor_falls_back_to_plausible_older_year(self, monkeypatch):
        # Anchor book_value=100 / shares_out=1_000_000 -> bvps=0.0001 -> pb=100000 (>1000 bound).
        # An older year has stockholders_equity=$5,000,000 -> bvps=5.0 -> pb=2.0, plausible.
        loader = _make_loader(monkeypatch, [(Decimal("5000000.00"),)])

        result = loader._compute_valuations(
            symbol="SYM",
            current_price=10.0,
            shares_out=1_000_000.0,
            ttm_eps=None,
            ttm_revenue=None,
            book_value=100.0,
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["pb_ratio"] == 2.0

    def test_implausible_anchor_with_no_plausible_fallback_stays_null(self, monkeypatch):
        loader = _make_loader(monkeypatch, [(Decimal("200.00"),)])

        result = loader._compute_valuations(
            symbol="SYM",
            current_price=10.0,
            shares_out=1_000_000.0,
            ttm_eps=None,
            ttm_revenue=None,
            book_value=100.0,
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["pb_ratio"] is None

    def test_immaterial_bvps_under_1000_ceiling_still_falls_back(self, monkeypatch):
        # Same day, same sweep, follow-up (see pe_ratio's ICUI case): the 1000 ceiling alone
        # doesn't catch every near-zero-per-share blowup. current_price=10, shares_out=
        # 1_000_000, book_value=50_000 -> bvps=0.05 -> pb=200 (UNDER 1000, accepted outright
        # pre-fix). An older year has stockholders_equity=$5,000,000 -> bvps=5.0 -> pb=2.0,
        # plausible.
        loader = _make_loader(monkeypatch, [(Decimal("5000000.00"),)])

        result = loader._compute_valuations(
            symbol="SYM",
            current_price=10.0,
            shares_out=1_000_000.0,
            ttm_eps=None,
            ttm_revenue=None,
            book_value=50_000.0,
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["pb_ratio"] == 2.0

    def test_immaterial_bvps_fallback_skips_another_immaterial_year(self, monkeypatch):
        # The fallback query includes the anchor year itself - a near-zero anchor bvps must
        # not just re-select itself.
        loader = _make_loader(monkeypatch, [(Decimal("50000.00"),), (Decimal("5000000.00"),)])

        result = loader._compute_valuations(
            symbol="SYM",
            current_price=10.0,
            shares_out=1_000_000.0,
            ttm_eps=None,
            ttm_revenue=None,
            book_value=50_000.0,
            ocf=None,
            capex=None,
            prior_year_eps=None,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["pb_ratio"] == 2.0
