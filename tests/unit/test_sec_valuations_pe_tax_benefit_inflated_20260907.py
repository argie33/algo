"""Regression test (2026-09-07, goal: "why does LLY score so far below distressed/turnaround
healthcare peers" audit): pe_ratio had no guard against net_income inflated by a one-off tax
benefit (a large negative income_tax_expense) relative to pretax_income - distinct from the
existing _pe_earnings_too_volatile guard (loss-years-then-a-profit-year), which doesn't fire when
the company has been GAAP-profitable for 3 straight years but this year's net_income is still
skewed well above pretax/operating earnings by a one-off tax item. Live-confirmed RIGL: FY2025
pretax_income $121.8M, net_income $367.0M off a -$245.2M income_tax_expense (effective tax rate
-201%) computed pe_ratio=2.39, ranking it #1 on the Value factor leaderboard ahead of every real
pharma major including LLY.
"""

from decimal import Decimal

from loaders.load_sec_valuations import SecValuationsLoader


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return self._row


class _FakeDatabaseContext:
    def __init__(self, row):
        self._row = row

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._row)

    def __exit__(self, *exc):
        return False


def _guard(monkeypatch, row):
    import loaders.helpers.sec_valuations_ratios as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(row))
    loader = SecValuationsLoader.__new__(SecValuationsLoader)
    return loader._pe_earnings_tax_benefit_inflated("SYM")


class TestPeEarningsTaxBenefitInflated:
    def test_rigl_shaped_tax_benefit_flagged(self, monkeypatch):
        # FY2025 pretax_income=121.827M, income_tax_expense=-245.197M (effective rate -201%).
        assert _guard(monkeypatch, (Decimal("121827000"), Decimal("-245197000"))) is True

    def test_ordinary_positive_effective_tax_rate_not_flagged(self, monkeypatch):
        # A normal taxpaying company: pretax=100, tax expense=25 (25% rate).
        assert _guard(monkeypatch, (Decimal("100"), Decimal("25"))) is False

    def test_modest_rd_credit_negative_rate_not_flagged(self, monkeypatch):
        # A mild R&D-credit-driven negative rate (-10%) is below the 30% threshold.
        assert _guard(monkeypatch, (Decimal("100"), Decimal("-10"))) is False

    def test_exactly_at_threshold_flagged(self, monkeypatch):
        # abs(tax) == 30% of pretax exactly - boundary is inclusive (>=).
        assert _guard(monkeypatch, (Decimal("100"), Decimal("-30"))) is True

    def test_pretax_loss_not_flagged(self, monkeypatch):
        # pretax_income <= 0 - the guard only concerns itself with inflating a profitable year.
        assert _guard(monkeypatch, (Decimal("-50"), Decimal("-100"))) is False

    def test_no_row_on_file_not_flagged(self, monkeypatch):
        assert _guard(monkeypatch, None) is False
