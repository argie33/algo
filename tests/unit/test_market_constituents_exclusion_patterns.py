"""Regression test: preferred-share/subordinated-debt securities that don't say the
literal word "preferred" must still be excluded from the common-equity universe.

Found live 2026-07-28: EXCLUSION_PATTERNS caught `\\bpreferred\\b` but missed "Preference
Shares" (different word), "Subordinated Debentures"/"Subordinated Notes" (junior debt),
and "Pfd Ser"/"Pfd Stock" (abbreviated depositary-share preferred notation) - all real
NASDAQ/NYSE listing-file phrasings. Confirmed live: 58 already-tracked symbols
(BAC$E, ALL$B, AFGC, DTB, RZC, ...) were `active=true` and flowing through technical
indicators/scoring/signals as if they were common equity. Also guards the negative case
that caused the fix to need care: BNS ("Bank Nova Scotia Halifax Pfd 3 Ordinary Shares")
is a real, actively-traded common ADR with a garbled security_name containing "Pfd" -
a bare `\\bpfd\\b` pattern would have wrongly excluded it.
"""

from loaders.load_market_constituents import should_exclude


class TestNewExclusionPatterns:
    def test_preference_shares_excluded(self):
        assert should_exclude(
            "Aspen Insurance Holdings Limited 5.625% Perpetual Non-Cumulative Preference Shares"
        )

    def test_subordinated_debentures_excluded(self):
        assert should_exclude("American Financial Group, Inc. 5.125% Subordinated Debentures due 2059")

    def test_subordinated_notes_excluded(self):
        assert should_exclude("Brookfield BRP Holdings (Canada) Inc. 4.875% Perpetual Subordinated Notes")

    def test_pfd_ser_excluded(self):
        assert should_exclude("Bank of America Corporation Depositary Sh repstg 1/1000th Perp Pfd Ser E")

    def test_pfd_stock_excluded(self):
        assert should_exclude(
            "U.S. Bancorp Depositary Shares, Each representing a 1/100th interest in a share of "
            "Series A Non-CumulativePerpetual Pfd Stock"
        )

    def test_garbled_common_adr_not_excluded(self):
        """BNS is a real, actively-traded common ADR - a garbled security_name containing
        'Pfd' must not exclude it. This is why the fix is `\\bpfd (ser|stock)`, not `\\bpfd\\b`."""
        assert not should_exclude("Bank Nova Scotia Halifax Pfd 3 Ordinary Shares")

    def test_ordinary_common_stock_not_excluded(self):
        assert not should_exclude("Apple Inc. - Common Stock")


class TestRightsWhenIssuedAndDepositaryShareExclusionPatterns:
    """Regression test added 2026-08-03: found while root-causing price_daily's chronic
    ~4% "missing symbol" completion gap. 28 already-active symbols turned out to be SPAC
    rights offerings, when-issued shares, or depositary-share/bare-percentage preferred
    notation - none of which yfinance has a ticker for at all, so they permanently failed
    every price-loader run while silently counting against the completion threshold.
    """

    def test_spac_rights_with_each_wording_excluded(self):
        assert should_exclude(
            "AI Infrastructure Acquisition Corp. Rights, each entitling the holder to "
            "receive one-fifth (1/5) of one Class A Ordinary Share"
        )

    def test_spac_rights_without_each_wording_excluded(self):
        assert should_exclude(
            "GalaxyEdge Acquisition Corporation Rights to receive one-fourth (1/4) of one ordinary share"
        )

    def test_when_issued_common_stock_excluded(self):
        assert should_exclude("Resideo Technologies, Inc. Common Stock When-Issued")

    def test_bare_percentage_series_preferred_excluded(self):
        assert should_exclude("DigitalBridge Group, Inc. 7.125% Series H")

    def test_depositary_shares_excluded(self):
        assert should_exclude("Equitable Holdings, Inc. Depositary Shares")

    def test_dep_shs_abbreviation_excluded(self):
        assert should_exclude(
            "Morgan Stanley Dep Shs Rpstg 1/1000th Int Prd Ser F Fxd to Flag"
        )

    def test_pfd_shs_ser_excluded(self):
        """Not caught by the existing `\\bpfd (ser|stock)` pattern - "Shs" sits between
        "Pfd" and "Ser" in the real listing-file text."""
        assert should_exclude("EPR Properties Series E Cumulative Conv Pfd Shs Ser E")

    def test_mccormick_common_stock_not_excluded(self):
        """MKC.V is a real common stock (McCormick) with an unusual ticker suffix in our
        DB - a data-hygiene question for the symbol table, not a text-exclusion candidate.
        Must not be caught by the new "Series"/rights patterns."""
        assert not should_exclude("McCormick & Company, Incorporated Common Stock")

    def test_sce_trust_not_excluded_by_these_patterns(self):
        """SCE TRUST VI is ambiguous with no distinguishing preferred/rights keyword - a
        bare `\\btrust\\b` pattern would risk false-positiving real REIT common stock, so
        it's deliberately left unmatched pending individual review."""
        assert not should_exclude("SCE TRUST VI")
