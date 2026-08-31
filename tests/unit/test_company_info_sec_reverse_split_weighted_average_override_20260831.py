"""Regression test for a 2026-08-31 fix (goal: data-coverage sweep, reverse-split follow-up to
sec_valuations_frozen_yfinance_snapshot_live_recheck_fixed_20260831) to load_company_info_sec.py.

Live-confirmed via FUBO (1-for-12 reverse split effective 2026-03-23) and AMRN (1-for-20,
2025-04-11): both `dei:EntityCommonStockSharesOutstanding` and
`us-gaap:CommonStockSharesOutstanding` simply stopped being tagged at all after the split - SEC's
own companyconcept API confirms FUBO has nothing past end=2025-09-30 despite 3 more 10-Qs filed
since. `_latest_shares_entry` (the existing 730-day staleness cutoff) happily accepts that
pre-split value since it's well within 2 years - it has no way to know a fresher truth exists.
`us-gaap:WeightedAverageNumberOfSharesOutstandingBasic` (a duration concept every filer needs for
its own EPS calc, so tagged far more reliably) DOES have the fresh post-split value.

Fix: after resolving shares_outstanding from the dei/us-gaap "instant" tiers, check whether
WeightedAverageNumberOfSharesOutstandingBasic has a candidate that is BOTH meaningfully fresher
(>=120 days newer `end`) AND meaningfully different (>=1.3x ratio) - only then override, so an
ordinary annual-only tagger (no split, just infrequent re-tagging) is untouched.
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions() -> dict:
    return {
        "name": "FuboTV Inc.",
        "sic": "4841",
        "sicDescription": "SERVICES-CABLE & OTHER PAY TELEVISION SERVICES",
        "entityType": "operating",
        "filings": {"recent": {"form": ["10-Q"]}},
    }


class TestReverseSplitWeightedAverageOverride:
    def test_stale_post_split_instant_concept_overridden_by_fresh_weighted_average(self) -> None:
        """FUBO-shaped: instant concept stuck at the pre-split ~342M count, but a fresher,
        smaller weighted-average count (post-split reality) exists - must be used instead."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0001484769"
        loader.sec_client.get_submissions.return_value = _submissions()
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {},
                "us-gaap": {
                    "CommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2025-09-30", "val": 342_664_855, "form": "10-Q"}]}
                    },
                    "WeightedAverageNumberOfSharesOutstandingBasic": {
                        "units": {"shares": [{"end": "2026-06-30", "val": 31_055_542, "form": "10-Q"}]}
                    },
                },
            }
        }

        result = loader.fetch_incremental("FUBO", None)

        assert result[0]["shares_outstanding"] == 31_055_542

    def test_fresh_instant_concept_not_overridden(self) -> None:
        """When the instant concept is already fresh (no split-driven gap), a stale-looking
        weighted-average candidate must not override a perfectly good current value."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0001484769"
        loader.sec_client.get_submissions.return_value = _submissions()
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {},
                "us-gaap": {
                    "CommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2026-06-30", "val": 31_000_000, "form": "10-Q"}]}
                    },
                    "WeightedAverageNumberOfSharesOutstandingBasic": {
                        "units": {"shares": [{"end": "2025-09-30", "val": 342_664_855, "form": "10-Q"}]}
                    },
                },
            }
        }

        result = loader.fetch_incremental("FUBO", None)

        assert result[0]["shares_outstanding"] == 31_000_000

    def test_small_ratio_difference_not_overridden(self) -> None:
        """A fresher weighted-average candidate that differs by less than 1.3x (ordinary
        dilution/buyback drift, not a split) must not trigger the override."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0001484769"
        loader.sec_client.get_submissions.return_value = _submissions()
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {},
                "us-gaap": {
                    "CommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2025-01-01", "val": 100_000_000, "form": "10-Q"}]}
                    },
                    "WeightedAverageNumberOfSharesOutstandingBasic": {
                        "units": {"shares": [{"end": "2026-06-30", "val": 110_000_000, "form": "10-Q"}]}
                    },
                },
            }
        }

        result = loader.fetch_incremental("TESTCO", None)

        assert result[0]["shares_outstanding"] == 100_000_000

    def test_small_freshness_gap_not_overridden(self) -> None:
        """A weighted-average candidate less than 120 days fresher must not trigger the
        override even with a large ratio - avoids noisy same-quarter comparisons."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0001484769"
        loader.sec_client.get_submissions.return_value = _submissions()
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {},
                "us-gaap": {
                    "CommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2026-05-01", "val": 342_000_000, "form": "10-Q"}]}
                    },
                    "WeightedAverageNumberOfSharesOutstandingBasic": {
                        "units": {"shares": [{"end": "2026-06-01", "val": 31_000_000, "form": "10-Q"}]}
                    },
                },
            }
        }

        result = loader.fetch_incremental("TESTCO2", None)

        assert result[0]["shares_outstanding"] == 342_000_000
