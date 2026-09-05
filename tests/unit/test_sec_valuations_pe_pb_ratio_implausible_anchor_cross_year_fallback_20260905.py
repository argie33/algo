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
    import loaders.load_sec_valuations as mod

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
