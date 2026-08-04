#!/usr/bin/env python3
"""Regression test: dividend record dedup must not collapse distinct dividends.

fetch_incremental previously deduped extracted dividend records on
(symbol, fiscal_year, fiscal_period) - fields never set on the record dicts, so
every record for a symbol matched the same (symbol, None, None) key and only the
first survived. A symbol with multiple fiscal years of declared dividends silently
lost all but one row before it ever reached the database.
"""

from unittest.mock import MagicMock

import pytest

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


def test_payment_date_is_not_fabricated() -> None:
    """SEC XBRL never reports a true payment date. ex_dividend_date is structurally
    estimated (period_end + 45d) because it doubles as this table's dedup/primary key
    (migration 1168), but payment_date has no such requirement - it must stay None
    rather than compound the estimate with a second guessed date presented as real."""
    loader = _make_loader()

    records = loader.fetch_incremental("TEST", since=None)

    assert records
    for r in records:
        assert r["payment_date"] is None
        assert r["record_date"] is None
        assert r["ex_dividend_date"] is not None


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


def test_split_restated_duplicate_period_keeps_earliest_filed_value() -> None:
    """A stock split retroactively restates historical per-share dividend values in later
    comparative filings - confirmed live against AAPL's real companyfacts: the
    2011-09-25..2012-09-29 period reports val=2.65 in the original 2012 10-K but val=0.38 in
    the 2014 10-K/2015 8-K after Apple's 2014 7-for-1 split. Since dividend_per_share is part
    of the primary key, both would otherwise survive as separate "distinct" dividends for the
    same real-world quarter. Only the earliest-filed (as originally declared, not restated)
    value must survive."""
    facts = {
        "facts": {
            "us-gaap": {
                "CommonStockDividendsPerShareDeclared": {
                    "units": {
                        "USD/shares": [
                            {"val": 2.65, "filed": "2012-10-31", "end": "2012-09-29"},
                            {"val": 2.65, "filed": "2013-10-30", "end": "2012-09-29"},
                            {"val": 0.38, "filed": "2014-10-27", "end": "2012-09-29"},
                            {"val": 0.38, "filed": "2015-01-28", "end": "2012-09-29"},
                        ]
                    }
                }
            }
        }
    }
    loader = _make_loader()
    loader.sec_client.get_company_facts.return_value = facts

    records = loader.fetch_incremental("TEST", since=None)

    assert len(records) == 1
    assert float(records[0]["dividend_per_share"]) == pytest.approx(2.65)
    assert records[0]["declaration_date"].isoformat() == "2012-10-31"


def test_unexpected_xbrl_unit_is_skipped_not_treated_as_per_share() -> None:
    """A per-share concept ("...PerShareDeclared") tagged under a unit other than the
    standard 'USD/shares' (filer XBRL error, restatement artifact) must not be silently
    ingested as dividend_per_share - there's no downstream sanity check on the value, so
    a plain-USD fact slipping through here would corrupt the field with no error raised."""
    facts = {
        "facts": {
            "us-gaap": {
                "CommonStockDividendsPerShareDeclared": {
                    "units": {
                        "USD/shares": [{"val": 0.24, "filed": "2023-01-30", "end": "2022-12-31"}],
                        "USD": [{"val": 12000000, "filed": "2023-01-30", "end": "2022-12-31"}],
                    }
                }
            }
        }
    }
    loader = _make_loader()
    loader.sec_client.get_company_facts.return_value = facts

    records = loader.fetch_incremental("TEST", since=None)

    assert len(records) == 1
    assert float(records[0]["dividend_per_share"]) == pytest.approx(0.24)


def test_declared_and_paid_disagreeing_amount_same_period_still_collapses() -> None:
    """Live bug, confirmed 2026-08-04: the outer cross-concept dedup in fetch_incremental
    used to key on (symbol, ex_dividend_date, dividend_per_share) - a 3-column key that
    never matched the real 2-column DB constraint (symbol, ex_dividend_date) established
    by migration 1168. CommonStockDividendsPerShareDeclared and
    CommonStockDividendsPerShareCashPaid estimate the identical ex_dividend_date for the
    same fiscal period (period_end + 45d) but routinely report slightly different
    per-share amounts (declared vs. actually paid), so the 3-column key let both survive
    as "distinct" - and the bulk upsert then crashed with
    "ON CONFLICT DO UPDATE command cannot affect row a second time" the moment both landed
    in the same insert batch. Live-reproduced on 608+ real symbols (ABBV, BA, CVX, COST,
    CVS, CSCO, ...) the first time this loader ran after the dedup key drifted out of sync
    with migration 1168. Must collapse to exactly one record per (symbol,
    ex_dividend_date), same as test_true_duplicate_on_primary_key_is_still_deduped's
    matching-amount case - declared is extended into `results` before paid, so it wins."""
    facts = {
        "facts": {
            "us-gaap": {
                "CommonStockDividendsPerShareDeclared": {
                    "units": {"USD/shares": [{"val": 0.24, "filed": "2023-01-30", "end": "2022-12-31"}]}
                },
                "CommonStockDividendsPerShareCashPaid": {
                    "units": {"USD/shares": [{"val": 0.23, "filed": "2023-01-30", "end": "2022-12-31"}]}
                },
            }
        }
    }
    loader = _make_loader()
    loader.sec_client.get_company_facts.return_value = facts

    records = loader.fetch_incremental("TEST", since=None)

    assert len(records) == 1
    assert float(records[0]["dividend_per_share"]) == pytest.approx(0.24)
    assert records[0]["source"] == "SEC_XBRL_CommonStockDividendsPerShareDeclared"
