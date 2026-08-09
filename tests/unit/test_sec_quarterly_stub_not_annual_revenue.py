"""Regression test for two compounding bugs found live 2026-08-09 via ORLY (O'Reilly
Automotive) showing a ~127,000% "gross margin" on the dashboard:

1. utils/external/sec_statements.py::_aggregate_concepts() accepted ANY fp (including
   Q1-Q4 single-quarter facts, ~90 days) into the annual "FY" bucket with no check on
   the fact's actual reporting span. For a company whose current fiscal year's 10-K
   hasn't been filed yet, this let a real single-quarter figure (e.g. Q1 revenue,
   ~$4B for ORLY) masquerade as if it were the full year's revenue - or, worse, let an
   unrelated single-quarter fact under a completely different concept fill the "FY"
   bucket when no annual data existed yet for the preferred concepts.

2. loaders/helpers/sec_base.py::transform()'s revenue field_mapping merge ("last
   concept iterated wins") let the InterestAndDividendIncomeOperating/
   InterestIncomeOperating bank/REIT revenue-proxy concepts unconditionally overwrite
   "revenue" even when a real revenue concept's value was already present for the same
   row - contradicting field_mapping's own documented intent ("only wins for filers
   with nothing else"). Live-confirmed: ORLY (a normal retailer, not a bank) reports a
   small real "interest and dividend income" line item (~$1.75M, interest on cash
   investments) that isn't its revenue at all.

Both are fixed here: (1) a duration check now rejects Q1-Q4-tagged facts under ~330
days for annual extraction, and (2) sec_base.py's transform() now supports
`fallback_only_fields` - sec_fields that only write into their target db_field when
nothing else already has.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000898173"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _quarter_entry(start: str, end: str, val: float, filed: str, fp: str, fy: int = 2026) -> dict:
    return {"start": start, "end": end, "val": val, "filed": filed, "fp": fp, "fy": fy, "form": "10-Q"}


class TestQuarterlyFactNotAcceptedAsAnnual:
    def test_single_quarter_duration_rejected_from_annual_bucket(self):
        facts = {
            "us-gaap": {
                # Only a Q1 revenue fact exists so far this calendar year (FY2026 10-K not
                # filed yet) - must NOT populate the fiscal_year=2026 "FY" bucket.
                "SalesRevenueNet": {
                    "units": {
                        "USD": [
                            _quarter_entry("2026-01-01", "2026-03-31", 4_400_000_000.0, "2026-05-08", "Q1"),
                        ]
                    }
                },
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "ORLY", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert 2026 not in by_year, "a single quarter's fact must not seed an annual FY row"

    def test_full_year_span_tagged_as_quarterly_still_accepted(self):
        # A YTD/full-year cumulative fact that happens to carry a quarterly fp (e.g. some
        # Q4 filings) should still be usable for annual extraction.
        facts = {
            "us-gaap": {
                "SalesRevenueNet": {
                    "units": {
                        "USD": [
                            _quarter_entry("2025-01-01", "2025-12-31", 16_000_000_000.0, "2026-02-15", "Q4"),
                        ]
                    }
                },
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "ORLY", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["sales_revenue_net"] == 16_000_000_000.0

    def test_quarter_fact_mistagged_fp_fy_still_rejected_from_annual_bucket(self):
        # WIDENED 2026-08-09 (same day, later session): live-confirmed via AAT (American
        # Assets Trust, a REIT) that SEC XBRL sometimes tags a genuinely 90-day comparative
        # entry with fp='FY' (not just Q1-Q4) - the original fix above only guarded
        # fp in ('Q1'-'Q4'), so this case slipped through and understated AAT's real
        # ~$457M FY2024 revenue down to a $110.7M single-quarter fragment. A real full-year
        # fp='FY' entry for the SAME fiscal year (span >= 330 days) must still win.
        facts = {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            # Genuinely 90-day span, but tagged fp='FY' - must be rejected.
                            _quarter_entry("2024-01-01", "2024-03-31", 110_695_000.0, "2026-02-06", "FY"),
                            # The real full-year figure for the same fiscal_year=2024 bucket.
                            _quarter_entry("2024-01-01", "2024-12-31", 457_855_000.0, "2026-02-06", "FY"),
                        ]
                    }
                },
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "AAT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2024]["revenues"] == 457_855_000.0


class TestRevenueFallbackOnlyWinsWhenNothingElsePresent:
    def _make_loader(self):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "sales_revenue_net": "revenue",
            "interest_and_dividend_income_operating": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_and_dividend_income_operating"})
        return loader

    def test_fallback_does_not_overwrite_real_revenue(self):
        loader = self._make_loader()
        # Same row carries BOTH a real revenue value and the bank/REIT fallback concept -
        # this is exactly the ORLY case (real retail revenue + a small unrelated interest
        # income line item reported under the fallback concept's tag).
        row = {
            "symbol": "ORLY",
            "fiscal_year": 2025,
            "sales_revenue_net": 16_000_000_000.0,
            "interest_and_dividend_income_operating": 1_748_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 16_000_000_000.0

    def test_fallback_still_wins_when_nothing_else_present(self):
        loader = self._make_loader()
        row = {
            "symbol": "FNWB",
            "fiscal_year": 2025,
            "interest_and_dividend_income_operating": 42_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 42_000_000.0
