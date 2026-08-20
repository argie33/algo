"""Regression test: cash_per_share_unavailable_reason must distinguish a missing
shares_outstanding (the exact sec_valuations.shares_outstanding column already given its own
specific "shares_outstanding_unavailable" reason everywhere else in this codebase - Ownership
data unresolved category) from a genuinely missing total_cash SEC concept.

Found live 2026-08-19 ("no SEC data" audit continuation): cash_per_share = total_cash_ev /
shares_outstanding, both hardcoded to the same generic "missing_sec_data" regardless of which
input was actually missing. Live-confirmed 771 of 860 universe cash_per_share "missing_sec_data"
rows have a real total_cash on file but shares_outstanding unavailable - the same deterministic
gate market_cap/pb_ratio/ps_ratio's own sec_valuations.reason propagation fix already surfaces.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _NullCursor:
    """_compute_quality_metrics fires several unrelated fallback-year lookups (interest_expense,
    ROIC tax triple, ROIC balance sheet pair) that must all resolve to "no better data found"
    (not a real DB error) so only the cash_per_share computation under test is exercised."""

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _FakeDatabaseContext:
    def __enter__(self):
        return _NullCursor()

    def __exit__(self, *exc):
        return False


def _quality_row(shares_outstanding=None):
    """34-element quality_row matching _compute_quality_metrics' index layout (index 11 =
    shares_outstanding). current_assets/current_liabilities always populated so the function
    doesn't take its early "every core metric is None" exit."""
    row = [None] * 34
    row[0] = 1000.0  # stockholders_equity
    row[3] = 100.0  # net_income
    row[6] = 500.0  # current_assets
    row[7] = 100.0  # current_liabilities
    row[11] = shares_outstanding
    return row


class TestCashPerShareSharesOutstandingReason:
    def test_missing_shares_outstanding_gets_specific_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value = _FakeDatabaseContext()
            metrics = loader._compute_quality_metrics(
                "NOSHARES", _quality_row(shares_outstanding=None), ev_metrics=(None, 5_000_000.0, None)
            )

        assert metrics.get("cash_per_share") is None
        assert metrics["cash_per_share_unavailable_reason"] == "shares_outstanding_unavailable"

    def test_missing_total_cash_keeps_generic_reason(self):
        # Control: shares_outstanding IS present, only total_cash is missing - must keep the
        # generic reason, not misattribute the gap to shares_outstanding.
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value = _FakeDatabaseContext()
            metrics = loader._compute_quality_metrics(
                "NOCASH", _quality_row(shares_outstanding=1_000_000.0), ev_metrics=(None, None, None)
            )

        assert metrics.get("cash_per_share") is None
        assert metrics["cash_per_share_unavailable_reason"] == "missing_sec_data"

    def test_both_present_computes_real_value(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value = _FakeDatabaseContext()
            metrics = loader._compute_quality_metrics(
                "BOTHOK", _quality_row(shares_outstanding=1_000_000.0), ev_metrics=(None, 5_000_000.0, None)
            )

        assert metrics.get("cash_per_share") == 5.0
        assert metrics.get("cash_per_share_unavailable_reason") is None
