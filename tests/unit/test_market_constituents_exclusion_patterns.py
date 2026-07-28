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
