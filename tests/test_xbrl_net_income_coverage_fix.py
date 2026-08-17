#!/usr/bin/env python3
"""Test XBRL net income extraction fix for 466 companies with 0% coverage.

This test verifies the fixes for:
1. ETFs and quarterly-only reporters (EE) - accept quarterly data for annual extraction
2. IFRS-only filers (ONON, ATHE) - add fallback net income concepts
3. Proxy statement data (fp=None) - include annual data from non-10K/10Q filings
"""

import pytest

from utils.external.sec_edgar_client import SecEdgarClient
from utils.external.sec_statements import get_income_statement


class TestNetIncomeCoverageFix:
    """Verify net income extraction works for previously broken companies."""

    @pytest.fixture
    def client(self):
        return SecEdgarClient()

    def test_gld_spdr_gold_trust_has_net_income(self, client):
        """GLD (SPDR Gold Trust) - ETF with net income data.

        Checks across all statements, not just the latest: GLD's SEC filer has
        been observed to tag EarningsPerShareBasic but omit NetIncomeLoss from
        XBRL in its most recent 10-Q(s) - real upstream filing drift, not a
        coverage-extraction bug (confirmed live 2026-08-04: 15/20 historical
        statements have net_income_loss populated, only the newest 10-Q lacks
        it). Asserting on statements[-1] alone makes this test flake every
        time SEC's own tagging lags for the latest quarter - same robust
        "any statement" pattern already used by the EE/ATHE cases below.
        """
        statements = get_income_statement(client, "GLD", period="annual")
        assert len(statements) > 0, "GLD should have annual income statements"

        net_incomes = [s.get("net_income_loss") for s in statements]
        assert any(v is not None for v in net_incomes), "GLD should have net_income_loss in at least one statement"

    def test_ee_ishares_etf_has_net_income(self, client):
        """EE (iShares ETF) - quarterly-only reporter, now accepts quarterly data."""
        statements = get_income_statement(client, "EE", period="annual")
        assert len(statements) > 0, "EE should have annual income statements"

        # At least some statements should have net_income (mixing Q1 quarterly data
        # and proxy statement annual data)
        net_incomes = [s.get("net_income_loss") for s in statements]
        assert any(v is not None for v in net_incomes), "EE should have net_income in at least some statements"

    def test_onon_on_holding_ifrs_filer_has_no_usd_net_income(self, client):
        """ONON (On Holding) - IFRS-only filer, CHF-denominated - correctly excluded.

        SUPERSEDED 2026-08-17 by the non-USD currency guard in _aggregate_concepts
        (utils/external/sec_statements.py): this test originally (2026-08-01) asserted
        ONON's ProfitLossAttributableToOwnersOfParent alias populated net_income_loss.
        Live-confirmed via ONON's real companyfacts JSON: ALL 31 of its
        ProfitLossAttributableToOwnersOfParent entries are tagged unit="CHF" - it has
        no USD-denominated net income fact anywhere (only one incidental USD concept
        in its entire ifrs-full taxonomy: CashAndCashEquivalents). The currency guard
        now correctly skips these CHF facts rather than writing Swiss-franc magnitudes
        into a column documented as USD - same "no reliable per-filer FX rate, don't
        fabricate" reasoning as the rejected NumberOfSharesOutstanding IFRS alias and
        the SHG/MUFG/SMFG non-USD Assets exclusions in the same file. Restoring the old
        assertion would require reverting that guard, reintroducing a real ~magnitude
        data-quality bug for the sake of this one test - so the test is updated to
        assert the current, correct behavior instead.
        """
        statements = get_income_statement(client, "ONON", period="annual")
        # ONON has no us-gaap facts at all and its only income-statement-relevant IFRS
        # concepts (revenue, profit) are CHF-only, so once the currency guard correctly
        # excludes them, _aggregate_concepts has nothing left to build a row from -
        # zero rows, not rows with a None net_income_loss.
        assert statements == [], (
            f"ONON has no USD-denominated income-statement concepts (all CHF) - expected "
            f"zero rows, got {len(statements)}"
        )

    def test_athe_athena_ifrs_filer_has_no_usd_net_income(self, client):
        """ATHE (Athena) - IFRS-only filer, AUD-denominated - correctly excluded.

        SUPERSEDED 2026-08-17, same root cause and reasoning as
        test_onon_on_holding_ifrs_filer_has_no_usd_net_income above. Live-confirmed via
        ATHE's real companyfacts JSON: its ComprehensiveIncome fallback concept is
        tagged unit="AUD" (Australian dollars), not USD.
        """
        statements = get_income_statement(client, "ATHE", period="annual")
        assert len(statements) > 0, "ATHE should still have annual income statement rows (from its us-gaap facts)"

        net_incomes = [s.get("net_income_loss") for s in statements]
        assert not any(v is not None for v in net_incomes), (
            "ATHE's only net-income concept (ComprehensiveIncome) is AUD-denominated with "
            "no USD equivalent - net_income_loss should stay None rather than silently "
            "treat AUD as USD"
        )

    def test_rani_aytu_has_net_income(self, client):
        """RANI (Aytu BioPharma) - us-gaap filer, should still work."""
        statements = get_income_statement(client, "RANI", period="annual")
        assert len(statements) > 0, "RANI should have annual income statements"

        latest = statements[-1]
        assert latest.get("net_income_loss") is not None, "RANI should have net_income_loss"

    def test_sngx_has_net_income(self, client):
        """SNGX - us-gaap filer with quarterly data, now accepts quarterly.

        Checks across all statements, not just the latest: live-verified 2026-08-10,
        SNGX's newest fiscal year (2026, still mid-year) has no net_income_loss tagged
        yet, but all 15 prior years (2011-2025) do - same real upstream filing-lag
        pattern as GLD above, not a coverage-extraction bug. Asserting on
        statements[-1] alone flakes every time the current fiscal year is incomplete.
        """
        statements = get_income_statement(client, "SNGX", period="annual")
        assert len(statements) > 0, "SNGX should have annual income statements"

        net_incomes = [s.get("net_income_loss") for s in statements]
        assert any(v is not None for v in net_incomes), "SNGX should have net_income_loss in at least one statement"

    def test_aifc_has_net_income(self, client):
        """AIFC - us-gaap filer with mixed FY and quarterly data.

        Checks across all statements, not just the latest: live-verified 2026-08-10,
        AIFC's newest fiscal year (2026, still mid-year) has no net_income_loss tagged
        yet, but 10 prior years do - same real upstream filing-lag pattern as GLD
        above, not a coverage-extraction bug.
        """
        statements = get_income_statement(client, "AIFC", period="annual")
        assert len(statements) > 0, "AIFC should have annual income statements"

        net_incomes = [s.get("net_income_loss") for s in statements]
        assert any(v is not None for v in net_incomes), "AIFC should have net_income_loss in at least one statement"
