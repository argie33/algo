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

    def test_onon_on_holding_ifrs_filer_has_net_income(self, client):
        """ONON (On Holding) - IFRS-only filer, uses fallback net income concepts."""
        statements = get_income_statement(client, "ONON", period="annual")
        assert len(statements) > 0, "ONON should have annual income statements"

        # ONON reports ProfitLossAttributableToOwnersOfParent in IFRS, which is now
        # mapped to net_income_loss via fallback aliases
        latest = statements[-1]
        assert latest.get("net_income_loss") is not None, (
            "ONON should have net_income_loss (from IFRS ProfitLossAttributableToOwnersOfParent)"
        )

    def test_athe_athena_ifrs_filer_has_net_income(self, client):
        """ATHE (Athena) - IFRS-only filer, uses ComprehensiveIncome fallback."""
        statements = get_income_statement(client, "ATHE", period="annual")
        assert len(statements) > 0, "ATHE should have annual income statements"

        # ATHE reports ComprehensiveIncome in IFRS, which is now mapped to
        # net_income_loss via fallback aliases
        net_incomes = [s.get("net_income_loss") for s in statements]
        assert any(v is not None for v in net_incomes), "ATHE should have net_income in at least some statements"

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
