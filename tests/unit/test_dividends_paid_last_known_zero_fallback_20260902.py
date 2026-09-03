"""Regression test for the 2026-09-02 follow-up fix (goal: "Missing SEC/XBRL data" reduction):
[[dividends_paid_prior_year_fallback_added_20260902]]'s single-year-back fallback correctly
recovered BLK's anchor-year gap but explicitly did NOT recover CCL/CMS, whose gap spans 3+
consecutive fiscal years - a prior-year lookback that's also None doesn't help.

Live-confirmed via real SEC companyfacts: CCL's `PaymentsOfDividends` was tagged $0 for
FY2021/FY2022 (dividend suspended) and never tagged again for FY2023-2025 - a common preparer
pattern of omitting an immaterial/zero line item from XBRL once it stays zero, not a fact
change. CMS's most recent tag was a real non-zero $546M (FY2022) with nothing since - a
materially different shape (a real payer whose tag vanished) that must NOT be carried forward,
since a stale non-zero figure risks overstating a since-changed/cut dividend. Only the "last
known value was exactly $0" subset is safe to carry forward indefinitely.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(stockholders_equity=1000.0, net_income=100.0, dividends_paid=None, prior_year_dividends_paid=None):
    row = [None] * 35
    row[0] = stockholders_equity
    row[3] = net_income
    row[6] = 500.0  # current_assets
    row[7] = 100.0  # current_liabilities
    row[15] = dividends_paid
    row[34] = prior_year_dividends_paid
    return row


class _ZeroDividendsCursor:
    """Returns one symbol from the last-known-zero-dividends query, empty for everything else."""

    def __init__(self, zero_symbols):
        self._zero_symbols = zero_symbols
        self.queries: list[str] = []

    def execute(self, query, params=None):
        self.queries.append(query)

    def fetchone(self):
        return None

    def fetchall(self):
        if self.queries and "ranked" in self.queries[-1] and "dividends_paid = 0" in self.queries[-1]:
            return [(s,) for s in self._zero_symbols]
        return []


class TestDividendsPaidLastKnownZeroFallback:
    def test_last_known_zero_multi_year_gap_recovers_as_zero_payout(self):
        loader = _make_loader()
        cur = _ZeroDividendsCursor(zero_symbols=["CCL"])
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cur
            metrics = loader._compute_quality_metrics(
                "CCL",
                _quality_row(
                    stockholders_equity=5_000_000_000.0,
                    net_income=1_000_000_000.0,
                    dividends_paid=None,
                    prior_year_dividends_paid=None,
                ),
            )

        assert metrics["payout_ratio"] == 0.0
        assert metrics.get("payout_ratio_unavailable_reason") is None

    def test_stale_nonzero_last_known_value_not_carried_forward(self):
        # CMS-shape: most recent tag was real and non-zero, but from a fiscal year further
        # back than one year ago - must stay unresolved (not in the zero-carryforward set),
        # never fabricated as a stale-but-nonzero payout.
        loader = _make_loader()
        cur = _ZeroDividendsCursor(zero_symbols=[])  # CMS's last known value wasn't $0
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cur
            metrics = loader._compute_quality_metrics(
                "CMS",
                _quality_row(
                    stockholders_equity=5_000_000_000.0,
                    net_income=1_000_000_000.0,
                    dividends_paid=None,
                    prior_year_dividends_paid=None,
                ),
            )

        assert metrics.get("payout_ratio") is None

    def test_not_consulted_when_prior_year_already_recovers(self):
        # The zero-carryforward query must never fire once the one-year-back fallback already
        # resolved a value - same "pure in-memory substitution only on a genuine gap"
        # discipline as the prior-year fallback itself.
        loader = _make_loader()
        cur = _ZeroDividendsCursor(zero_symbols=["BLK"])
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cur
            loader._compute_quality_metrics(
                "BLK",
                _quality_row(
                    stockholders_equity=55_888_000_000.0,
                    net_income=5_553_000_000.0,
                    dividends_paid=None,
                    prior_year_dividends_paid=2_500_000_000.0,
                ),
            )

        assert not any("ranked" in q and "dividends_paid = 0" in q for q in cur.queries)
