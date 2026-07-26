#!/usr/bin/env python3
"""Regression test: dividend record dedup must not collapse distinct dividends.

fetch_incremental previously deduped extracted dividend records on
(symbol, fiscal_year, fiscal_period) - fields never set on the record dicts, so
every record for a symbol matched the same (symbol, None, None) key and only the
first survived. A symbol with multiple fiscal years of declared dividends silently
lost all but one row before it ever reached the database.
"""

from unittest.mock import MagicMock

from loaders.load_dividend_data import DividendDataLoader

COMPANY_FACTS = {
    "facts": {
        "us-gaap": {
            "CommonStockDividendsPerShareDeclared": {
                "units": {
                    "USD/shares": [
                        {"val": 0.24, "filed": "2023-01-30", "end": "2022-12-31"},
                        {"val": 0.23, "filed": "2022-01-28", "end": "2021-12-31"},
                    ]
                }
            }
        }
    }
}


def _make_loader() -> DividendDataLoader:
    # Bypass OptimalLoader.__init__ (DB/infra wiring not needed to exercise the
    # pure extraction + dedup logic in fetch_incremental).
    loader = DividendDataLoader.__new__(DividendDataLoader)
    loader.sec_client = MagicMock()
    loader.sec_client.symbol_to_cik.return_value = "0000320193"
    loader.sec_client.get_company_facts.return_value = COMPANY_FACTS
    return loader


def test_distinct_dividend_records_are_not_collapsed() -> None:
    loader = _make_loader()

    records = loader.fetch_incremental("TEST", since=None)

    assert len(records) == 2, f"expected 2 distinct dividend records, got {len(records)}: {records}"
    per_share = {r["dividend_per_share"] for r in records}
    assert len(per_share) == 2


def test_true_duplicate_on_primary_key_is_still_deduped() -> None:
    facts = {
        "facts": {
            "us-gaap": {
                "CommonStockDividendsPerShareDeclared": {
                    "units": {"USD/shares": [{"val": 0.24, "filed": "2023-01-30", "end": "2022-12-31"}]}
                },
                "CommonStockDividendsPerShareCashPaid": {
                    "units": {"USD/shares": [{"val": 0.24, "filed": "2023-01-30", "end": "2022-12-31"}]}
                },
            }
        }
    }
    loader = _make_loader()
    loader.sec_client.get_company_facts.return_value = facts

    records = loader.fetch_incremental("TEST", since=None)

    # Both XBRL concepts report the same amount for the same estimated ex-date -
    # same primary key (symbol, ex_dividend_date, dividend_per_share) - must collapse
    # to one row or the DB upsert fails with "ON CONFLICT DO UPDATE... row a second time".
    assert len(records) == 1
