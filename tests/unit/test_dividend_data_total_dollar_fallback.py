"""Regression test for loaders/load_dividend_data.py's total-dollar dividend fallback.

Live sampling of symbols marked no_dividend_xbrl_concepts despite a real, positive
value_metrics.dividend_yield found the dominant remaining pattern (~75% of a random
60-symbol sample, once already-fixed IFRS/currency cases were excluded) is filers that
tag a real cash dividend only as a TOTAL DOLLAR AMOUNT XBRL concept
(PaymentsOfDividendsCommonStock/DividendsCommonStockCash/PaymentsOfDividends for US GAAP,
DividendsPaid-family for IFRS), never any per-share concept - live-confirmed via DHR, STZ,
FOXA, VALE, IR. Deriving dividend_per_share via total / shares-outstanding was rejected as
too error-prone (multi-class share structures like STZ's would silently produce a wrong
per-share value) - this stores the real, unmodified total instead, in the
previously-always-NULL total_dividend_amount column, leaving dividend_per_share NULL
rather than guessed.
"""

from decimal import Decimal

from loaders.load_dividend_data import (
    _TOTAL_DIVIDEND_CONCEPTS_GAAP,
    _TOTAL_DIVIDEND_CONCEPTS_IFRS,
    DividendDataLoader,
)


def _loader() -> DividendDataLoader:
    return DividendDataLoader.__new__(DividendDataLoader)


class TestTotalDollarFallback:
    def test_extracts_total_dividend_amount_from_payments_of_dividends_common_stock(self):
        us_gaap = {
            "PaymentsOfDividendsCommonStock": {
                "units": {
                    "USD": [
                        {
                            "start": "2025-01-01",
                            "end": "2025-03-31",
                            "val": 538800000,
                            "filed": "2025-04-22",
                        }
                    ]
                }
            }
        }
        results = _loader()._extract_total_dividends_from_xbrl_concept("STZ", us_gaap, "PaymentsOfDividendsCommonStock")
        assert len(results) == 1
        r = results[0]
        assert r["total_dividend_amount"] == Decimal("538800000")
        assert r["dividend_per_share"] is None
        assert r["data_unavailable"] is False
        assert r["source"] == "SEC_XBRL_TOTAL_PaymentsOfDividendsCommonStock"

    def test_ifrs_total_concept_extracted_from_ifrs_taxonomy(self):
        ifrs = {
            "DividendsPaid": {
                "units": {
                    "USD": [
                        {
                            "start": "2025-10-01",
                            "end": "2025-12-31",
                            "val": 3561000000,
                            "filed": "2026-03-27",
                        }
                    ]
                }
            }
        }
        results = _loader()._extract_total_dividends_from_xbrl_concept("VALE", ifrs, "DividendsPaid")
        assert len(results) == 1
        assert results[0]["total_dividend_amount"] == Decimal("3561000000")

    def test_instant_fact_without_start_is_rejected(self):
        # Total-dollar concepts represent a period total, unlike the per-share concepts
        # which can legitimately be instant facts - a fact missing `start` must not be
        # mistaken for a period total.
        us_gaap = {
            "PaymentsOfDividends": {"units": {"USD": [{"end": "2025-03-31", "val": 100000000, "filed": "2025-04-22"}]}}
        }
        results = _loader()._extract_total_dividends_from_xbrl_concept("X", us_gaap, "PaymentsOfDividends")
        assert results == []

    def test_non_major_currency_unit_rejected(self):
        # BRL/CLP/COP-style emerging-market currencies stay behind the fail-closed guard,
        # same discipline as the per-share extraction and sec_statements.py's FX handling.
        ifrs = {
            "DividendsPaid": {
                "units": {"BRL": [{"start": "2025-01-01", "end": "2025-12-31", "val": 5000000, "filed": "2026-03-01"}]}
            }
        }
        results = _loader()._extract_total_dividends_from_xbrl_concept("X", ifrs, "DividendsPaid")
        assert results == []

    def test_implausible_magnitude_rejected(self):
        us_gaap = {
            "PaymentsOfDividends": {
                "units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 10**14, "filed": "2026-01-01"}]}
            }
        }
        results = _loader()._extract_total_dividends_from_xbrl_concept("X", us_gaap, "PaymentsOfDividends")
        assert results == []

    def test_zero_value_skipped(self):
        us_gaap = {
            "PaymentsOfDividends": {
                "units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 0, "filed": "2026-01-01"}]}
            }
        }
        results = _loader()._extract_total_dividends_from_xbrl_concept("X", us_gaap, "PaymentsOfDividends")
        assert results == []

    def test_missing_concept_returns_empty(self):
        results = _loader()._extract_total_dividends_from_xbrl_concept("X", {}, "PaymentsOfDividends")
        assert results == []

    def test_fetch_incremental_only_tries_total_fallback_when_per_share_empty(self, monkeypatch):
        # A filer with real per-share data must never fall through to the total-dollar
        # concepts too - that would double-count the same real-world dividend under two
        # different ex_dividend_date estimates derived from the same period.
        loader = _loader()
        loader.sec_client = None

        us_gaap_with_per_share = {
            "CommonStockDividendsPerShareDeclared": {
                "units": {
                    "USD/shares": [
                        {"end": "2025-03-31", "val": 0.5, "filed": "2025-04-22"},
                    ]
                }
            },
            "PaymentsOfDividends": {
                "units": {
                    "USD": [{"start": "2025-01-01", "end": "2025-03-31", "val": 500000000, "filed": "2025-04-22"}]
                }
            },
        }

        def fake_fetch(self, symbol, timeout_sec=20.0):
            return {
                "cik": "1",
                "facts_response": {"facts": {"us-gaap": us_gaap_with_per_share, "ifrs-full": {}}},
            }

        monkeypatch.setattr(DividendDataLoader, "_fetch_sec_data_with_timeout", fake_fetch)

        results = loader.fetch_incremental("X", None)
        assert all(r["dividend_per_share"] is not None for r in results if not r.get("data_unavailable"))
        assert not any(r.get("source", "").startswith("SEC_XBRL_TOTAL_") for r in results)

    def test_concept_lists_are_ordered_most_specific_first(self):
        # PaymentsOfDividendsCommonStock (common-only) must precede the broader
        # PaymentsOfDividends (may include preferred/NCI at some filers) so the dedup-by-
        # ex-date "first occurrence wins" logic in fetch_incremental prefers precision.
        assert _TOTAL_DIVIDEND_CONCEPTS_GAAP.index(
            "PaymentsOfDividendsCommonStock"
        ) < _TOTAL_DIVIDEND_CONCEPTS_GAAP.index("PaymentsOfDividends")
        assert _TOTAL_DIVIDEND_CONCEPTS_IFRS.index(
            "DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities"
        ) < _TOTAL_DIVIDEND_CONCEPTS_IFRS.index("DividendsPaid")
