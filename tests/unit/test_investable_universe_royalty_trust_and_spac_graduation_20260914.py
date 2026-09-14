"""Regression test: `investable_universe_conditions()` doesn't blanket-exclude real operating
companies that share a legacy SIC code with genuine shells/trusts.

Found 2026-09-14 (`/goal` session, adversarial leaderboard audit - user pushback: "I would
have wanted to buy TPL when it popped off last year, that doesn't seem right"). The original
SIC-6792 ("Oil Royalty Traders") exclusion was a blanket `sic_code IN (...)` check with no
name/substance signal - it correctly excludes genuine zero-employee pass-through trusts
(CRT/MTR/PBT/SBR/SJT/NRT, all literally named "... Royalty Trust") but also permanently
excluded TPL (Texas Pacific Land Corp, converted from trust to corporation in 2021, a real
operating business with a growing Water Services segment), LB (LandBridge Co LLC, real and
growing revenue), and EROK (EagleRock Land LLC, real revenue) - all real, tradeable
companies that happen to carry the same legacy SEC SIC code, live-confirmed against SEC
EDGAR directly (not a stale value in our own data).

Same root problem, different SIC code: SIC 6770 ("Blank Checks") correctly excludes
pre-merger SPAC shells, but a completed de-SPAC keeps the same SIC with no update - INV
(Innventure, Inc.) completed its business combination October 2024 and is a real operating
company with real revenue, but was excluded by SIC alone.

Fixed with general, self-updating signals instead of one-off ticker carve-outs: SIC 6792 is
only excluded when `security_name` also contains "Trust" (every genuine trust has this in its
name; none of the 3 real operating companies do). SIC 6770 is only excluded when the symbol
has never reported positive annual revenue (a completed de-SPAC has real revenue; a
still-pre-merger shell reports exactly $0.00, live-verified for CEPO/GIX).

These are fragment-content checks only, not live-DB assertions against TPL/LB/INV/CRT/etc -
tests/conftest.py forces DB_NAME=algo_trading (a separate, deliberately near-empty DB) for
the whole pytest run, so a live query against these specific real symbols would silently
return empty regardless of correctness. The real symbols were verified directly against the
actual local dev DB (`stocks`) outside pytest before this fix landed - see this fix's own
commit message for those results.
"""

from algo.signals.investable_universe import investable_universe_conditions


class TestInvestableUniverseRoyaltyTrustAndSpacGraduation:
    def test_fragment_requires_trust_in_name_for_sic_6792_exclusion(self):
        fragment = investable_universe_conditions("s", "sy")
        assert "sic_code = 6792" in fragment
        assert "security_name ~* 'Trust'" in fragment

    def test_fragment_requires_no_revenue_for_sic_6770_exclusion(self):
        fragment = investable_universe_conditions("s", "sy")
        assert "sic_code = 6770" in fragment
        assert "FROM annual_income_statement WHERE revenue > 0" in fragment

    def test_fragment_still_excludes_sic_6189(self):
        fragment = investable_universe_conditions("s", "sy")
        assert "sic_code = 6189" in fragment
