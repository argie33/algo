"""Regression tests for two real fallback gaps in get_balance_sheet()
(utils/external/sec_balance_sheet.py) - goal: "under 500" push, total_debt_not_itemized
investigation, 2026-09-10.

1. DCX (Digital Currency X Technology, a 20-F filer) tags a real, continuous
   "LongTermDebtCurrent" ($95.16M FY2024/$96.96M FY2025) with NO "LongTermDebtNoncurrent"
   sibling ever - live-confirmed via real SEC companyfacts JSON. Before this fix,
   _fill_long_term_debt_from_noncurrent_current_split only ever used `current` when
   `noncurrent` was also present (`noncurrent is not None` gated both of its branches), so
   a Current-only filer's real debt figure was popped and silently discarded, leaving
   long_term_debt NULL despite total_liabilities/stockholders_equity both being populated.

2. MWG (a different 20-F filer) tags real, continuous us-gaap
   "FinanceLeaseLiabilityCurrent"/"FinanceLeaseLiabilityNoncurrent" (summing to ~$5.1M
   FY2025) and "OperatingLeaseLiabilityCurrent"/"OperatingLeaseLiabilityNoncurrent", but
   never the combined "FinanceLeaseLiability"/"OperatingLeaseLiability" concepts that were
   the only ones fetched before this fix - live-confirmed via real SEC companyfacts JSON.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000078003"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


def _entry(end: str, val: float, filed: str, fy: int = 2025) -> dict:
    return {"end": end, "val": val, "filed": filed, "fp": "FY", "fy": fy, "form": "20-F"}


class TestLongTermDebtCurrentOnlyFallback:
    def test_dcx_shaped_current_only_no_noncurrent_sibling(self):
        facts = {
            "us-gaap": {
                "LongTermDebtCurrent": _concept([_entry("2025-12-31", 96_962_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "DCX", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["long_term_debt"] == 96_962_000.0
        assert "long_term_debt_current" not in by_year[2025]
        assert "long_term_debt_noncurrent" not in by_year[2025]

    def test_real_long_term_debt_concept_not_overwritten_by_current_only_fallback(self):
        facts = {
            "us-gaap": {
                "LongTermDebt": _concept([_entry("2025-12-31", 100_000_000.0, "2026-02-25")]),
                "LongTermDebtCurrent": _concept([_entry("2025-12-31", 5_000_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["long_term_debt"] == 100_000_000.0

    def test_zero_current_only_does_not_assert_debt_free(self):
        """PGR-shaped (2026-09-16, SEC-vs-yfinance divergence sweep): a filer that tags a
        real "$0 due within 12 months" LongTermDebtCurrent fact, with no LongTermDebtNoncurrent
        sibling and no other debt concept resolved, must NOT have long_term_debt asserted as
        0 - that's only informative about near-term maturities, never a stand-in for the
        total. Before the 2026-09-16 fix, `current is not None` treated this same $0 fact as
        "confirmed debt-free", live-confirmed wrong for PGR/WTFC/DKS/AMP/IBKR (all real,
        continuing debt the pipeline just hadn't resolved a value for that year).
        """
        facts = {
            "us-gaap": {
                "LongTermDebtCurrent": _concept([_entry("2025-12-31", 0.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST4", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025].get("long_term_debt") is None
        assert "long_term_debt_current" not in by_year[2025]


class TestDksUnsecuredDebtConceptFixed:
    """Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep):
    DKS (Dick's Sporting Goods) tags its entire real $1.484B senior notes under plain
    "UnsecuredDebt" - live-confirmed via real SEC companyfacts JSON (period end
    2025-02-01: $1,484,217,000) - never tagging LongTermDebt/SeniorNotes/NotesPayable/
    DebtInstrumentCarryingAmount. This concept was never fetched at all, so DKS fell
    through to the LongTermDebtCurrent=0 misread (its own separate fix, above) and landed
    on a false debt-free 0 instead of its real debt load.
    """

    def _make_loader(self):
        from loaders.helpers.sec_base import SecEdgarStatementLoader

        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "unsecured_debt": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"unsecured_debt"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_unsecured_debt_to_long_term_debt(self) -> None:
        from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS

        assert _BALANCE_FIELD_MAPPING["unsecured_debt"] == "long_term_debt"
        assert "unsecured_debt" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_dks_style_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "DKS",
            "fiscal_year": 2025,
            "unsecured_debt": 1_484_217_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 1_484_217_000.0

    def test_unsecured_debt_never_overwrites_a_real_long_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "long_term_debt": 95_281_000_000.0,
            "unsecured_debt": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 95_281_000_000.0


class TestUsGaapLeaseLiabilityCurrentNoncurrentSplitFallback:
    def test_mwg_shaped_finance_and_operating_lease_split(self):
        facts = {
            "us-gaap": {
                "FinanceLeaseLiabilityCurrent": _concept([_entry("2025-12-31", 2_529_000.0, "2026-02-25")]),
                "FinanceLeaseLiabilityNoncurrent": _concept([_entry("2025-12-31", 2_582_000.0, "2026-02-25")]),
                "OperatingLeaseLiabilityCurrent": _concept([_entry("2025-12-31", 1_000_000.0, "2026-02-25")]),
                "OperatingLeaseLiabilityNoncurrent": _concept([_entry("2025-12-31", 4_000_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "MWG", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["finance_lease_liability"] == 5_111_000.0
        assert by_year[2025]["operating_lease_liability"] == 5_000_000.0
        assert "finance_lease_liability_current" not in by_year[2025]
        assert "finance_lease_liability_noncurrent" not in by_year[2025]
        assert "operating_lease_liability_current" not in by_year[2025]
        assert "operating_lease_liability_noncurrent" not in by_year[2025]

    def test_only_one_half_tagged_stays_null_not_partial_sum(self):
        facts = {
            "us-gaap": {
                "FinanceLeaseLiabilityCurrent": _concept([_entry("2025-12-31", 2_529_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST2", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025].get("finance_lease_liability") is None

    def test_real_combined_concept_not_overwritten_by_split_fallback(self):
        facts = {
            "us-gaap": {
                "FinanceLeaseLiability": _concept([_entry("2025-12-31", 1_230_000_000.0, "2026-02-25")]),
                "FinanceLeaseLiabilityCurrent": _concept([_entry("2025-12-31", 999_000_000.0, "2026-02-25")]),
                "FinanceLeaseLiabilityNoncurrent": _concept([_entry("2025-12-31", 999_000_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST3", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["finance_lease_liability"] == 1_230_000_000.0
