"""Regression test for the bank/thrift revenue-collision bug found live 2026-08-22
(goal session: real-money-readiness audit), a follow-up to the same-day AROW community-
bank revenue-gap fix.

WAFDP (Washington Federal, a bank holding company, SIC 6035) live-confirmed via real
companyfacts JSON: its real total revenue-equivalent (net interest income + noninterest
income) is tagged under interest_and_dividend_income_operating (FY2018=$607.1M,
FY2019=$671.5M - growing, consistent with real net_income), but it also tags a small,
real non-interest fee-income line under the ASC-606 "contract with customer" concept
(FY2018=$25.9M, FY2019=$24.9M). Bank interest income is explicitly out of ASC 606's
scope (same reasoning as the REIT/insurance cases in test_sec_reit_lease_revenue_not_
overwritten.py), so this ASC-606 tag is always the minor line for a bank, never the
total - but loaders/helpers/sec_base.py::transform()'s general priority chain let it
supersede interest_and_dividend_income_operating anyway (true for most post-2018
filers, wrong here), a ~23x understatement. A DB-wide scan (bank/thrift SIC codes,
revenue < 80% of net_income) found 40 more rows with the same signature (ALLY, AMTB,
AUBN, and others).

Fixed by extending the same depository-institution-symbol check
(_get_depository_institution_symbols(), already used elsewhere in this file for the
bank-capex-is-structurally-zero case) into the REIT/insurance ASC-606 fallback-only
gate.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestBankInterestIncomeNotOverwrittenByAscContractRevenue:
    def _make_loader(self, depository_symbols: frozenset[str]) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "interest_and_dividend_income_operating": "revenue",
            "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_and_dividend_income_operating"})
        loader._reit_only_fallback_fields = frozenset({"revenue_from_contract_with_customer_excluding_assessed_tax"})
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        loader._depository_institution_symbols = depository_symbols
        return loader

    def test_bank_real_interest_income_not_overwritten_by_minor_asc606_fee_income(self) -> None:
        loader = self._make_loader(depository_symbols=frozenset({"WAFDP"}))
        row = {
            "symbol": "WAFDP",
            "fiscal_year": 2018,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 25_904_000.0,
            "interest_and_dividend_income_operating": 607_083_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 607_083_000.0

    def test_bank_asc606_fee_income_still_wins_when_no_interest_income_present(self) -> None:
        loader = self._make_loader(depository_symbols=frozenset({"WAFDP"}))
        row = {
            "symbol": "WAFDP",
            "fiscal_year": 2018,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 25_904_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 25_904_000.0

    def test_non_bank_still_uses_normal_priority_asc606_wins(self) -> None:
        # Same shape of data, but the symbol isn't in the depository-institution set - a
        # normal post-2018 filer where the ASC-606 tag legitimately supersedes any small
        # incidental interest income line must be completely unaffected by this carve-out.
        loader = self._make_loader(depository_symbols=frozenset({"WAFDP"}))
        row = {
            "symbol": "ORLY",
            "fiscal_year": 2025,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 391_000_000_000.0,
            "interest_and_dividend_income_operating": 5_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 391_000_000_000.0
