"""Regression test for classify_stuck_symbol()
(scripts/fix_stuck_available_but_null_financial_statement_flags.py) - the one-time
retroactive-correction script for annual_balance_sheet/annual_income_statement/
annual_cash_flow/quarterly_balance_sheet/quarterly_income_statement/quarterly_cash_flow rows
stuck data_unavailable=FALSE/reason=NULL with every required field NULL (2026-09-10, live-
confirmed 478 rows/95 symbols across the six tables). Exercises the classification precedence
directly (each case corresponds to a real, live-confirmed symbol bucket from that sweep -
see the script's own module docstring/classify_stuck_symbol() docstring for the evidence)
without touching the DB or the network - client/company_info are fully mocked.
"""

from typing import Any
from unittest.mock import MagicMock

from scripts.fix_stuck_available_but_null_financial_statement_flags import classify_stuck_symbol


def _client(
    cik: str | Exception = "0001234567",
    facts: dict[str, Any] | Exception | None = None,
) -> MagicMock:
    client = MagicMock()
    if isinstance(cik, Exception):
        client.symbol_to_cik.side_effect = cik
    else:
        client.symbol_to_cik.return_value = cik
    if isinstance(facts, Exception):
        client.get_company_facts.side_effect = facts
    else:
        client.get_company_facts.return_value = facts if facts is not None else {"facts": {}}
    return client


class TestClassifyStuckSymbol:
    def test_shared_issuer_cik_symbol_wins_regardless_of_everything_else(self) -> None:
        # SVIX/UVIX (real 2026-09-10 stuck-bucket members) share CIK 0001793497 - the
        # SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS check must short-circuit before any lookup.
        client = _client(cik=ValueError("should never be called"))
        reason = classify_stuck_symbol("SVIX", "cashflow", client, {})
        assert reason == "shared_issuer_or_trust_cik_not_attributable"
        client.symbol_to_cik.assert_not_called()

    def test_unresolvable_symbol_gets_cik_not_found(self) -> None:
        # HONIV/ZBAI/AMPGR/EOSER (real stuck-bucket members) never resolve via SEC's ticker
        # cache or its browse-edgar fallback.
        client = _client(cik=ValueError("Symbol HONIV not found in SEC ticker cache"))
        reason = classify_stuck_symbol("HONIV", "balance", client, {})
        assert reason == "cik_not_found"

    def test_company_info_has_annual_report_filing_false_gets_no_annual_report_filing(self) -> None:
        client = _client()
        company_info = {
            "NEWCO": {
                "is_foreign_private_issuer": False,
                "entity_type": "operating",
                "sic_code": 2834,
                "has_annual_report_filing": False,
            }
        }
        reason = classify_stuck_symbol("NEWCO", "income", client, company_info)
        assert reason == "no_annual_report_filing"
        client.get_company_facts.assert_not_called()

    def test_cef_signature_gets_registered_investment_company_variant(self) -> None:
        """Same entity_type/sic_code CEF signature
        company_info_sec_reason_cleanup.py's reclassify_stale_registered_investment_company_reason()
        already uses - reused here rather than the generic reason."""
        client = _client()
        company_info = {
            "SOMECEF": {
                "is_foreign_private_issuer": False,
                "entity_type": "other",
                "sic_code": None,
                "has_annual_report_filing": False,
            }
        }
        reason = classify_stuck_symbol("SOMECEF", "balance", client, company_info)
        assert reason == "registered_investment_company_no_annual_report"

    def test_no_companyfacts_cached_at_all_gets_no_annual_report_filing(self) -> None:
        """A CIK resolves but SEC has zero companyfacts for it (404) - genuinely never filed,
        same reason as has_annual_report_filing=False."""
        client = _client(facts=FileNotFoundError("no companyfacts"))
        reason = classify_stuck_symbol("NEWLISTING", "cashflow", client, {})
        assert reason == "no_annual_report_filing"

    def test_fpi_with_only_rejected_currency_fact_gets_unsupported_currency_reason(self) -> None:
        # CEPU/CRESY/IRS/LOMA/BBAR/BMA-shaped: real Argentine FPI tagging Assets only under ARS.
        client = _client(
            facts={
                "facts": {
                    "ifrs-full": {
                        "Assets": {"units": {"ARS": [{"val": 500, "fy": 2024}]}},
                    }
                }
            }
        )
        company_info = {
            "CEPU": {
                "is_foreign_private_issuer": True,
                "entity_type": "other",
                "sic_code": 4911,
                "has_annual_report_filing": True,
            }
        }
        reason = classify_stuck_symbol("CEPU", "balance", client, company_info)
        assert reason == "unsupported_currency_no_fx_rate"

    def test_fpi_with_real_usd_fact_falls_to_generic_reason(self) -> None:
        client = _client(facts={"facts": {"us-gaap": {"Assets": {"units": {"USD": [{"val": 500, "fy": 2024}]}}}}})
        company_info = {
            "REALFPI": {
                "is_foreign_private_issuer": True,
                "entity_type": "operating",
                "sic_code": 2834,
                "has_annual_report_filing": True,
            }
        }
        reason = classify_stuck_symbol("REALFPI", "balance", client, company_info)
        assert reason == "incomplete_sec_filing_balance"

    def test_domestic_symbol_not_in_company_info_falls_to_generic_reason(self) -> None:
        # FXA/FXB/.../FFIC/ZKP-shaped: real distinct CIK, no company_info_sec row at all (not
        # an FPI question we have any signal on) - must never guess FPI-currency.
        # get_company_facts() IS still called here (no company_info_sec row means no
        # has_annual_report_filing signal, so the has-any-companyfacts-at-all check still
        # runs) - it just returns real data, so classification falls through to generic.
        client = _client(facts={"facts": {"us-gaap": {}}})
        reason = classify_stuck_symbol("FXA", "balance", client, {})
        assert reason == "incomplete_sec_filing_balance"

    def test_reason_is_scoped_to_the_requested_statement_type(self) -> None:
        client = _client(facts={"facts": {"us-gaap": {}}})
        assert classify_stuck_symbol("SOMECO", "income", client, {}) == "incomplete_sec_filing_income"
        assert classify_stuck_symbol("SOMECO", "cashflow", client, {}) == "incomplete_sec_filing_cashflow"
