"""Regression test for loaders/load_dividend_data.py's custom-extension currency-aware
dividend fallback, added 2026-09-12.

Root cause: a prior fix (2026-09-11, commit cccdef15f) registered PAYP in
sec_custom_xbrl_concepts.py's CUSTOM_DIVIDEND_CONCEPTS - but that registry is only ever
consumed by fetch_custom_dividends() via financial_statements_custom_extension_
fallbacks.py, wired into ConsolidatedFinancialStatementsLoader (annual_cash_flow.
dividends_paid), never into DividendDataLoader (the dividend_data table this bucket
actually tracks). Live-reconfirmed via a targeted rerun after that fix had landed:
dividend_data.data_unavailable_reason stayed "no_us_gaap_facts" for PAYP regardless.
Separately, PAYP's concept is tagged in JPY (unitRef="U_JPY", live-confirmed against the
real FY2026 20-F) - CUSTOM_DIVIDEND_CONCEPTS's own extractor has no currency handling at
all, so reusing it as-is would have misread JPY311,000,000 as USD311,000,000, a ~150x
overstatement. This fallback uses the currency-aware duration extractor instead
(sec_custom_xbrl_currency_duration.py) via a dedicated
_CUSTOM_DIVIDEND_CONCEPTS_CURRENCY_AWARE registry local to this loader.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from loaders.load_dividend_data import DividendDataLoader


def _loader() -> DividendDataLoader:
    loader = DividendDataLoader.__new__(DividendDataLoader)
    loader.sec_client = None
    return loader


class TestExtractCustomExtensionDividends:
    def test_registered_symbol_gets_currency_converted_records(self):
        loader = _loader()
        with patch(
            "utils.external.sec_custom_xbrl_concepts._fetch_custom_concept",
            return_value={2024: 1_183_940.74, 2025: 1_893_990.10, 2026: 1_949_843.26},
        ):
            results = loader._extract_custom_extension_dividends("PAYP", date(2026, 9, 12))

        assert len(results) == 3
        by_year = {r["declaration_date"].year: r for r in results}
        assert by_year[2024]["total_dividend_amount"] == Decimal("1183940.74")
        assert by_year[2024]["dividend_per_share"] is None
        assert by_year[2024]["data_unavailable"] is False
        assert by_year[2024]["source"] == "SEC_XBRL_CUSTOM_EXTENSION"
        # PAYP's real fiscal year ends March 31 (see _CUSTOM_DIVIDEND_FISCAL_YEAR_END) -
        # declaration_date must reflect that, not a generic Dec 31.
        assert by_year[2024]["declaration_date"] == date(2024, 3, 31)
        from datetime import timedelta

        assert by_year[2024]["ex_dividend_date"] == date(2024, 3, 31) + timedelta(days=45)

    def test_unregistered_symbol_returns_empty_without_any_fetch(self):
        loader = _loader()
        with patch("utils.external.sec_custom_xbrl_concepts._fetch_custom_concept") as mock_fetch:
            results = loader._extract_custom_extension_dividends("AAPL", date(2026, 9, 12))
        assert results == []
        mock_fetch.assert_not_called()

    def test_empty_fetch_result_returns_empty_not_a_marker(self):
        loader = _loader()
        with patch("utils.external.sec_custom_xbrl_concepts._fetch_custom_concept", return_value={}):
            results = loader._extract_custom_extension_dividends("PAYP", date(2026, 9, 12))
        assert results == []

    def test_zero_value_year_is_skipped(self):
        loader = _loader()
        with patch(
            "utils.external.sec_custom_xbrl_concepts._fetch_custom_concept",
            return_value={2024: 0.0, 2025: 1_893_990.10},
        ):
            results = loader._extract_custom_extension_dividends("PAYP", date(2026, 9, 12))
        assert len(results) == 1
        assert results[0]["declaration_date"].year == 2025

    def test_default_fiscal_year_end_is_december_31_for_unlisted_symbol(self):
        loader = _loader()
        loader._CUSTOM_DIVIDEND_CONCEPTS_CURRENCY_AWARE = {
            **DividendDataLoader._CUSTOM_DIVIDEND_CONCEPTS_CURRENCY_AWARE,
            "ZZZZ": [("zzzz", "SomeDividendConcept")],
        }
        with patch(
            "utils.external.sec_custom_xbrl_concepts._fetch_custom_concept",
            return_value={2025: 500_000.0},
        ):
            results = loader._extract_custom_extension_dividends("ZZZZ", date(2026, 9, 12))
        assert results[0]["declaration_date"] == date(2025, 12, 31)


class TestFetchIncrementalFallsBackToCustomExtension:
    def test_empty_companyfacts_tries_custom_extension_before_classifying_no_us_gaap_facts(self):
        """The exact bug this fix closes: companyfacts genuinely empty (us_gaap={},
        ifrs_full={}) must try the custom-extension fallback BEFORE falling to the
        generic no_us_gaap_facts/registered_investment_company classification."""
        loader = _loader()
        loader.sec_client = None

        with (
            patch.object(
                DividendDataLoader,
                "_fetch_sec_data_with_timeout",
                return_value={"facts_response": {"facts": {}}},
            ),
            patch.object(
                DividendDataLoader,
                "_extract_custom_extension_dividends",
                return_value=[{"symbol": "PAYP", "total_dividend_amount": 1_949_843.26}],
            ) as mock_custom,
            patch.object(DividendDataLoader, "_classify_no_gaap_or_ifrs_facts") as mock_classify,
        ):
            results = loader.fetch_incremental("PAYP", since=None)

        mock_custom.assert_called_once()
        mock_classify.assert_not_called()
        assert results == [{"symbol": "PAYP", "total_dividend_amount": 1_949_843.26}]

    def test_empty_companyfacts_with_no_custom_extension_still_classifies_as_before(self):
        loader = _loader()
        loader.sec_client = None

        with (
            patch.object(
                DividendDataLoader,
                "_fetch_sec_data_with_timeout",
                return_value={"facts_response": {"facts": {}}},
            ),
            patch.object(DividendDataLoader, "_extract_custom_extension_dividends", return_value=[]),
            patch.object(
                DividendDataLoader,
                "_classify_no_gaap_or_ifrs_facts",
                return_value={"symbol": "AAPL", "data_unavailable_reason": "no_us_gaap_facts"},
            ) as mock_classify,
        ):
            results = loader.fetch_incremental("AAPL", since=None)

        mock_classify.assert_called_once()
        assert results == [{"symbol": "AAPL", "data_unavailable_reason": "no_us_gaap_facts"}]


class TestCustomDividendConceptsCurrencyAwareRegistry:
    def test_registry_is_well_formed(self):
        for symbol, concepts in DividendDataLoader._CUSTOM_DIVIDEND_CONCEPTS_CURRENCY_AWARE.items():
            assert isinstance(symbol, str) and symbol
            assert concepts
            for prefix, local_name in concepts:
                assert isinstance(prefix, str) and prefix
                assert isinstance(local_name, str) and local_name

    def test_payp_is_registered(self):
        assert "PAYP" in DividendDataLoader._CUSTOM_DIVIDEND_CONCEPTS_CURRENCY_AWARE
