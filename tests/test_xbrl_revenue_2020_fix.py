#!/usr/bin/env python3
"""Test XBRL revenue extraction fix for 2020+ years in financial services companies.

This test verifies the fix for missing 2020+ revenue data in financial services
companies that switched from reporting "Revenues" (2007-2019) to
"RevenuesNetOfInterestExpense" (2013+, primary metric from 2020+).

Background:
- Before fix: Morgan Stanley, Wells Fargo, Xcel Energy had no revenue data for 2020+
- Root cause: Parser only looked for legacy "Revenues" concept, missing the newer
  "RevenuesNetOfInterestExpense" concept used by banks starting 2020
- Fix: Added RevenuesNetOfInterestExpense to income statement concept list
"""

import pytest

from utils.external.sec_edgar_client import SecEdgarClient
from utils.external.sec_statements import get_income_statement


class TestRevenueExtraction2020Fix:
    """Verify revenue extraction works for 2020+ years in financial services companies."""

    @pytest.fixture
    def client(self):
        return SecEdgarClient()

    def test_morgan_stanley_has_2020_plus_revenue(self, client):
        """MS - Investment bank with RevenuesNetOfInterestExpense for 2020+."""
        statements = get_income_statement(client, "MS", period="annual")

        # Extract 2020+ years with revenue
        revenues_2020_plus = {}
        for stmt in statements:
            year = stmt.get("fiscal_year")
            if year and year >= 2020:
                # RevenuesNetOfInterestExpense should be extracted as snake_case key
                revenue = stmt.get("revenues_net_of_interest_expense") or stmt.get("revenues")
                if revenue is not None:
                    revenues_2020_plus[year] = revenue

        # Before fix: 0 years, After fix: 7 years (2020-2026)
        assert len(revenues_2020_plus) >= 5, (
            f"MS should have at least 5 years of 2020+ revenue data, "
            f"got {len(revenues_2020_plus)}: {revenues_2020_plus}"
        )

        # Spot-check sample values
        # 2020 Q1 10-Q reported $48.757B
        if 2020 in revenues_2020_plus:
            assert revenues_2020_plus[2020] > 1_000_000_000, (
                f"MS 2020 revenue should be billions, got {revenues_2020_plus[2020]}"
            )

    def test_wells_fargo_has_2020_plus_revenue(self, client):
        """WFC - Bank with mix of Revenues (2020) and RevenuesNetOfInterestExpense (2021+)."""
        statements = get_income_statement(client, "WFC", period="annual")

        # Extract 2020+ years with revenue
        revenues_2020_plus = {}
        for stmt in statements:
            year = stmt.get("fiscal_year")
            if year and year >= 2020:
                # Should have either key (Revenues for 2020, RevenuesNetOfInterestExpense for 2021+)
                revenue = stmt.get("revenues_net_of_interest_expense") or stmt.get("revenues")
                if revenue is not None:
                    revenues_2020_plus[year] = revenue

        # After fix: 7 years (2020-2026)
        assert len(revenues_2020_plus) >= 6, (
            f"WFC should have at least 6 years of 2020+ revenue data, "
            f"got {len(revenues_2020_plus)}: {revenues_2020_plus}"
        )

        # Spot-check values
        # 2020 can have either Revenues (~$54.4B) or RevenuesNetOfInterestExpense (~$74.3B)
        # depending on which quarterly data is aggregated (10-Q contains various quarters)
        # The key point is we have revenue data, not the exact value
        if 2020 in revenues_2020_plus:
            assert revenues_2020_plus[2020] > 40_000_000_000, (
                f"WFC 2020 revenue should be > $40B, got {revenues_2020_plus[2020]}"
            )

    def test_xcel_energy_has_revenue(self, client):
        """XEL - Utility with continuous revenue reporting (utility doesn't switch concepts)."""
        statements = get_income_statement(client, "XEL", period="annual")

        # Extract years with revenue (should have continuous data)
        revenues_by_year = {}
        for stmt in statements:
            year = stmt.get("fiscal_year")
            if year:
                revenue = stmt.get("revenues_net_of_interest_expense") or stmt.get("revenues")
                if revenue is not None:
                    revenues_by_year[year] = revenue

        # Utilities typically report Revenues continuously (don't switch to
        # RevenuesNetOfInterestExpense like banks do), so we expect pre-2020 data
        assert len(revenues_by_year) > 0, "XEL should have revenue data"

        # Spot-check: should have at least some 2010s-2020s data
        recent_years = [y for y in revenues_by_year.keys() if y >= 2015]
        assert len(recent_years) > 0, f"XEL should have revenue for recent years (2015+), got {recent_years}"

    def test_revenue_extraction_key_names(self, client):
        """Verify that RevenuesNetOfInterestExpense is extracted with correct snake_case key."""
        statements = get_income_statement(client, "MS", period="annual")

        # Find a 2020+ statement that should have RevenuesNetOfInterestExpense
        for stmt in statements:
            year = stmt.get("fiscal_year")
            if year and year >= 2020:
                # Should have revenues_net_of_interest_expense key
                # (snake_case version of RevenuesNetOfInterestExpense)
                assert "revenues_net_of_interest_expense" in stmt, (
                    f"MS FY{year} should have 'revenues_net_of_interest_expense' key, got keys: {list(stmt.keys())}"
                )
                assert stmt["revenues_net_of_interest_expense"] is not None, (
                    f"MS FY{year} revenues_net_of_interest_expense should have a value"
                )
                break
