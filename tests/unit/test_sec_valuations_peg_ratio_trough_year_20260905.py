"""Regression test (2026-09-05, goal session: "implausible values" sweep, follow-up to the
pe_ratio/pb_ratio/ps_ratio immaterial-denominator fixes): peg_ratio must not compute a
spuriously near-zero value when prior_year_eps is a real but anomalous trough year relative to
the company's own multi-year EPS history.

A trough-year prior_year_eps makes growth_rate ((ttm_eps - prior_year_eps) / prior_year_eps)
mathematically enormous, which DEFLATES peg_ratio (the denominator) toward zero - the opposite
failure direction from pe/pb/ps ratio (whose immaterial denominators INFLATE the ratio past
their ceiling), so the existing `peg <= 10000` bound never catches it, and a fixed-dollar floor
(like pe_ratio's $0.10) doesn't either since a trough EPS isn't necessarily tiny in absolute
terms.

Live-confirmed via GILD: FY2024 EPS=$0.38 (real, litigation-charge trough year) vs
FY2021-2023's $4.96/$3.66/$4.54 (GILD's real normal range) - growth_rate=1700%,
peg=22.08/1700=0.01, while yfinance's own real trailingPegRatio for GILD is 2.03 (live-checked
directly). Also independently confirmed for AA/Alcoa. Uses the company's own EPS history as
ground truth (median of its other real positive years) rather than an invented magnitude cutoff.
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


def _make_loader(monkeypatch, history_rows):
    import loaders.load_sec_valuations as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(history_rows))
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestPegRatioTroughYear:
    def test_trough_year_prior_eps_stays_null(self, monkeypatch):
        # GILD-style: prior_year_eps=0.38 (trough), history shows real years at 4.96/3.66/4.54 -
        # median 4.54, 0.38 < 25% of that (1.135) - trough detected.
        loader = _make_loader(
            monkeypatch,
            [(Decimal("4.96"),), (Decimal("3.66"),), (Decimal("4.54"),), (Decimal("0.38"),)],
        )

        result = loader._compute_valuations(
            symbol="GILD",
            current_price=151.0,
            shares_out=1_000_000.0,
            ttm_eps=6.84,
            ttm_revenue=None,
            book_value=None,
            ocf=None,
            capex=None,
            prior_year_eps=0.38,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["pe_ratio"] is not None
        assert result.get("peg_ratio") is None

    def test_normal_yoy_growth_still_computes_peg_ratio(self, monkeypatch):
        # Control: prior_year_eps close to its own history (not a trough) must still produce
        # a real peg_ratio.
        loader = _make_loader(
            monkeypatch,
            [(Decimal("1.90"),), (Decimal("2.10"),), (Decimal("2.00"),)],
        )

        result = loader._compute_valuations(
            symbol="NORMALCO",
            current_price=50.0,
            shares_out=1_000_000.0,
            ttm_eps=2.20,
            ttm_revenue=None,
            book_value=None,
            ocf=None,
            capex=None,
            prior_year_eps=2.00,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["peg_ratio"] is not None
        assert result["peg_ratio"] > 0

    def test_insufficient_history_does_not_block_peg_ratio(self, monkeypatch):
        # Fewer than 2 other real years on file - can't judge trough-ness, so don't guess;
        # keep the existing (pre-fix) behavior of trusting prior_year_eps at face value.
        loader = _make_loader(monkeypatch, [(Decimal("2.00"),)])

        result = loader._compute_valuations(
            symbol="NEWCO",
            current_price=50.0,
            shares_out=1_000_000.0,
            ttm_eps=2.20,
            ttm_revenue=None,
            book_value=None,
            ocf=None,
            capex=None,
            prior_year_eps=2.00,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["peg_ratio"] is not None
