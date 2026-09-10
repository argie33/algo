"""Regression test for the 2026-09-09 fix (goal: "missing SEC/XBRL data under 500" sweep):
sustainable_growth_rate's dividend-TTM-recovery fallback used to blame the generic
"missing_sec_data" (Missing SEC/XBRL data) any time shares_outstanding was None, even when the
real cause was company_info_sec.shares_outstanding_unavailable_reason =
"fpi_shares_excluded_domestic_only" - a DELIBERATE exclusion for foreign private issuers (to
avoid a local-share/ADS-ratio unit mismatch), not a genuine SEC/XBRL extraction gap.

Live-confirmed via TX (Ternium S.A.)/CYD (China Yuchai)/AUXX/FGL/GAUZ/GIXI/INCR: all real,
current dividend payers with real positive net_income/stockholders_equity, all mislabeled this
way. Fixed by looking up company_info_sec.shares_outstanding_unavailable_reason and reusing it
verbatim when it's exactly "fpi_shares_excluded_domestic_only" (already correctly categorized as
"Legitimate / not applicable" in coverage_category_rules.py) - every other real "shares
genuinely unknown" cause (e.g. cik_not_found) keeps the pre-existing "missing_sec_data" label,
since this was never meant to touch those.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(stockholders_equity=1000.0, net_income=100.0, dividends_paid=None, shares_outstanding=None):
    row = [None] * 35
    row[0] = stockholders_equity
    row[3] = net_income
    row[6] = 500.0  # current_assets
    row[7] = 100.0  # current_liabilities
    row[11] = shares_outstanding
    row[15] = dividends_paid
    return row


class _RoutingCursor:
    """Mock cursor that returns real payer/TTM data plus a specific
    shares_outstanding_unavailable_reason, routed by query text - same pattern as the sibling
    dividends_paid_prior_year_fallback test."""

    def __init__(self, shares_reason):
        self._shares_reason = shares_reason
        self.queries: list[str] = []

    def execute(self, query, params=None):
        self.queries.append(query)
        self._last = query

    def fetchone(self):
        if "dividend_data" in self._last and "SUM" not in self._last:
            return (1,)  # has_real_dividend_history True
        if "shares_outstanding_unavailable_reason" in self._last:
            return (self._shares_reason,)
        return None

    def fetchall(self):
        return []


class TestSgrFpiSharesExcludedReason:
    def test_fpi_excluded_shares_gets_specific_reason_not_missing_sec_data(self):
        loader = _make_loader()
        cur = _RoutingCursor(shares_reason="fpi_shares_excluded_domestic_only")
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cur
            metrics = loader._compute_quality_metrics(
                "TX",
                _quality_row(
                    stockholders_equity=16_147_746_000.0,
                    net_income=303_095_000.0,
                    dividends_paid=None,
                    shares_outstanding=None,
                ),
            )

        assert metrics["sustainable_growth_rate"] is None
        assert metrics["sustainable_growth_rate_unavailable_reason"] == "fpi_shares_excluded_domestic_only"

    def test_other_shares_unavailable_causes_keep_missing_sec_data(self):
        # A genuine "shares outstanding is unknown for an unrelated reason" case (e.g.
        # cik_not_found) must not be swept into the FPI carve-out.
        loader = _make_loader()
        cur = _RoutingCursor(shares_reason="cik_not_found")
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cur
            metrics = loader._compute_quality_metrics(
                "NOCIK",
                _quality_row(
                    stockholders_equity=1000.0,
                    net_income=100.0,
                    dividends_paid=None,
                    shares_outstanding=None,
                ),
            )

        assert metrics["sustainable_growth_rate_unavailable_reason"] == "missing_sec_data"

    def test_shares_outstanding_present_never_hits_new_lookup(self):
        # Control: when shares_outstanding IS available, the TTM path is taken and the new
        # shares_outstanding_unavailable_reason lookup must never fire.
        loader = _make_loader()
        cur = _RoutingCursor(shares_reason="fpi_shares_excluded_domestic_only")
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cur
            loader._compute_quality_metrics(
                "HASSHARES",
                _quality_row(
                    stockholders_equity=1000.0,
                    net_income=100.0,
                    dividends_paid=None,
                    shares_outstanding=100.0,
                ),
            )

        assert not any("shares_outstanding_unavailable_reason" in q for q in cur.queries)
